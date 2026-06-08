import base64
import aiohttp
import jwt
import time
import uuid
import json
from datetime import datetime, timezone
from typing import Optional
import grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy import select, func

from services.chat import _dt_to_ts
from core.config import settings
from database import AsyncSessionLocal
from protobuf import mess_pb2, mess_pb2_grpc
from services.access_session import require_current_user_uuid
from services.models import Call, CallParticipant, ChatMember, DeviceToken
from services.enums import MemberStatus
from services.redis_client import redis_client
from livekit import api
from sqlalchemy.exc import IntegrityError

class CallServicer(mess_pb2_grpc.CallServiceServicer):
    # ---------- LiveKit HTTP API helpers (Basic Auth) ----------
    def _admin_token(self) -> str:
        now = int(time.time())
        payload = {
            "iss": settings.LIVEKIT_API_KEY,
            "exp": now + 3600,
            "nbf": now,
            "video": {
                "roomCreate": True,
                "roomDelete": True,
            },
        }
        return jwt.encode(payload, settings.LIVEKIT_API_SECRET, algorithm="HS256")
    def _basic_auth_header(self) -> str:
        credentials = f"{settings.LIVEKIT_API_KEY}:{settings.LIVEKIT_API_SECRET}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    async def _create_room(self, room_name: str):
        url = f"{settings.LIVEKIT_URL}/twirp/livekit.RoomService/CreateRoom"
        headers = {
            "Authorization": f"Bearer {self._admin_token()}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"name": room_name}, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"HTTP {resp.status}: {text}")

    async def _delete_room(self, room_name: str):
        url = f"{settings.LIVEKIT_URL}/twirp/livekit.RoomService/DeleteRoom"
        headers = {
            "Authorization": f"Bearer {self._admin_token()}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"room": room_name}, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    print(f"Warning: delete room failed: {text}")

    async def _generate_participant_token(self, room_name: str, user_id: str) -> tuple[str, str]:
        token = api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET) \
            .with_identity(user_id) \
            .with_name(user_id) \
            .with_grants(api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            )).to_jwt()
        return token, settings.LIVEKIT_WS_URL

    # ---------- Database & notifications ----------
    async def _get_chat_member_ids(self, session, chat_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(ChatMember.user_id).where(
            ChatMember.chat_id == chat_id,
            ChatMember.status == MemberStatus.active
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def _notify_call_update(self, call_id: str, event: str, payload: dict):
        async with AsyncSessionLocal() as session:
            call = await session.get(Call, uuid.UUID(call_id))
            if not call:
                return
            chat_id = call.chat_id
            member_ids = await self._get_chat_member_ids(session, chat_id)

        for user_id in member_ids:
            event_data = {"event": event, "payload": {"call_id": call_id, **payload}}
            await redis_client.publish(settings.REDIS_EVENTS_CHANNEL, json.dumps(event_data))
            is_online = await redis_client.is_user_online(str(user_id))
            if not is_online:
                await self._send_push_notification(user_id, event, payload)

    async def _send_push_notification(self, user_id: uuid.UUID, event: str, payload: dict):
        # Здесь должна быть реальная отправка push через APNs
        async with AsyncSessionLocal() as session:
            tokens = await session.execute(
                select(DeviceToken).where(
                    DeviceToken.user_id == user_id,
                    DeviceToken.device_type == "ios"
                )
            )
            for token_row in tokens.scalars():
                print(f"📱 Push to {token_row.device_token}: {event} {payload}")

    # ---------- gRPC methods ----------
    async def StartCall(self, request, context):
        user_uuid = await require_current_user_uuid(context)
        chat_uuid = uuid.UUID(request.chat_id)

        async with AsyncSessionLocal() as session:
            member_stmt = select(ChatMember).where(
                ChatMember.chat_id == chat_uuid,
                ChatMember.user_id == user_uuid,
                ChatMember.status == MemberStatus.active
            )
            if not (await session.execute(member_stmt)).scalar_one_or_none():
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a member")

            active_call = await session.execute(
                select(Call).where(
                    Call.chat_id == chat_uuid,
                    Call.status.in_(['pending', 'active'])
                )
            )
            if active_call.scalar_one_or_none():
                await context.abort(grpc.StatusCode.ALREADY_EXISTS, "Active call exists")

            room_name = str(uuid.uuid4())
            try:
                await self._create_room(room_name)
            except Exception as e:
                await context.abort(grpc.StatusCode.INTERNAL, f"LiveKit error: {e}")

            call = Call(
                chat_id=chat_uuid,
                initiator_id=user_uuid,
                status="pending",
                type=request.type,
                livekit_room_name=room_name
            )
            session.add(call)
            await session.flush()

            participant = CallParticipant(
                call_id=call.call_id,
                user_id=user_uuid,
                joined_at=datetime.now(timezone.utc)
            )
            session.add(participant)
            await session.commit()

            await self._notify_call_update(str(call.call_id), "call.incoming", {
                "chat_id": str(chat_uuid),
                "initiator_id": str(user_uuid),
                "type": request.type,
                "started_at": call.started_at.isoformat()
            })

            return self._call_to_proto(call)

    async def AcceptCall(self, request, context):
        user_uuid = await require_current_user_uuid(context)
        call_uuid = uuid.UUID(request.call_id)

        async with AsyncSessionLocal() as session:
            call = await session.get(Call, call_uuid)
            if not call:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Call not found")
            if call.status != "pending":
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Call already accepted or ended")

            # Проверка членства в чате
            member_stmt = select(ChatMember).where(
                ChatMember.chat_id == call.chat_id,
                ChatMember.user_id == user_uuid,
                ChatMember.status == MemberStatus.active
            )
            if not (await session.execute(member_stmt)).scalar_one_or_none():
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a member")

            # Добавляем участника звонка, если ещё не добавлен
            participant_stmt = select(CallParticipant).where(
                CallParticipant.call_id == call_uuid,
                CallParticipant.user_id == user_uuid
            )
            participant = (await session.execute(participant_stmt)).scalar_one_or_none()
            if not participant:
                participant = CallParticipant(
                    call_id=call_uuid,
                    user_id=user_uuid,
                    joined_at=datetime.now(timezone.utc)
                )
                session.add(participant)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()

            # Обновляем статус звонка
            call.status = "active"
            await session.commit()

            # Возвращаем полную информацию о звонке
            return mess_pb2.CallInfo(
                call_id=str(call.call_id),
                chat_id=str(call.chat_id),
                initiator_id=str(call.initiator_id),
                status=call.status,
                type=call.type,
                started_at=_dt_to_ts(call.started_at),
                # ended_at не заполняем, так как звонок ещё активен
            )

    async def RejectCall(self, request, context):
        user_uuid = await require_current_user_uuid(context)
        call_uuid = uuid.UUID(request.call_id)

        async with AsyncSessionLocal() as session:
            call = await session.get(Call, call_uuid)
            if not call or call.status != "pending":
                return Empty()

            if call.initiator_id != user_uuid:
                call.status = "declined"
                call.ended_at = datetime.now(timezone.utc)
                await session.commit()
                await self._notify_call_update(str(call_uuid), "call.ended", {"reason": "declined"})

        return Empty()

    async def EndCall(self, request, context):
        user_uuid = await require_current_user_uuid(context)
        call_uuid = uuid.UUID(request.call_id)

        async with AsyncSessionLocal() as session:
            call = await session.get(Call, call_uuid)
            if not call or call.status not in ("pending", "active"):
                return Empty()

            call.status = "completed" if call.status == "active" else "missed"
            call.ended_at = datetime.now(timezone.utc)
            await session.commit()

            await self._notify_call_update(str(call_uuid), "call.ended", {"reason": call.status})
            await self._delete_room(call.livekit_room_name)

        return Empty()

    async def GetCall(self, request, context):
        user_uuid = await require_current_user_uuid(context)
        call_uuid = uuid.UUID(request.call_id)

        async with AsyncSessionLocal() as session:
            call = await session.get(Call, call_uuid)
            if not call:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Call not found")

            member_stmt = select(ChatMember).where(
                ChatMember.chat_id == call.chat_id,
                ChatMember.user_id == user_uuid,
                ChatMember.status == MemberStatus.active
            )
            if not (await session.execute(member_stmt)).scalar_one_or_none():
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a member")

            return self._call_to_proto(call)

    async def ListCalls(self, request, context):
        user_uuid = await require_current_user_uuid(context)
        chat_uuid = uuid.UUID(request.chat_id)
        page = max(1, request.page)
        page_size = min(100, request.page_size or 20)
        offset = (page - 1) * page_size

        async with AsyncSessionLocal() as session:
            member_stmt = select(ChatMember).where(
                ChatMember.chat_id == chat_uuid,
                ChatMember.user_id == user_uuid,
                ChatMember.status == MemberStatus.active
            )
            if not (await session.execute(member_stmt)).scalar_one_or_none():
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a member")

            total = await session.scalar(select(func.count()).select_from(Call).where(Call.chat_id == chat_uuid))
            calls = (await session.execute(
                select(Call).where(Call.chat_id == chat_uuid)
                .order_by(Call.started_at.desc())
                .offset(offset).limit(page_size)
            )).scalars().all()

            return mess_pb2.CallsListResponse(
                calls=[self._call_to_proto(call) for call in calls],
                total_count=total or 0
            )

    async def GetLiveKitToken(self, request, context):
        user_uuid = await require_current_user_uuid(context)
        call_uuid = uuid.UUID(request.call_id)

        async with AsyncSessionLocal() as session:
            call = await session.get(Call, call_uuid)
            if not call:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Call not found")

            # Проверка членства в чате
            member_stmt = select(ChatMember).where(
                ChatMember.chat_id == call.chat_id,
                ChatMember.user_id == user_uuid,
                ChatMember.status == MemberStatus.active
            )
            if not (await session.execute(member_stmt)).scalar_one_or_none():
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a member")

            # Добавляем участника звонка, если ещё не добавлен
            participant_stmt = select(CallParticipant).where(
                CallParticipant.call_id == call_uuid,
                CallParticipant.user_id == user_uuid
            )
            participant = (await session.execute(participant_stmt)).scalar_one_or_none()
            if not participant:
                participant = CallParticipant(
                    call_id=call_uuid,
                    user_id=user_uuid,
                    joined_at=datetime.now(timezone.utc)
                )
                session.add(participant)
                try:
                    await session.commit()
                except IntegrityError:
                    # Если дубликат (например, из-за параллельного запроса), игнорируем
                    await session.rollback()
                    # Запись уже существует, ничего не делаем
            # Если участник уже был, просто продолжаем

            token, ws_url = await self._generate_participant_token(call.livekit_room_name, str(user_uuid))
            return mess_pb2.LiveKitTokenResponse(token=token, ws_url=ws_url)

    def _call_to_proto(self, call: Call) -> mess_pb2.CallInfo:
        started_ts = Timestamp()
        started_ts.FromDatetime(call.started_at)
        ended_ts = None
        if call.ended_at:
            ended_ts = Timestamp()
            ended_ts.FromDatetime(call.ended_at)

        return mess_pb2.CallInfo(
            call_id=str(call.call_id),
            chat_id=str(call.chat_id),
            initiator_id=str(call.initiator_id),
            status=call.status,
            type=call.type,
            started_at=started_ts,
            ended_at=ended_ts,
        )