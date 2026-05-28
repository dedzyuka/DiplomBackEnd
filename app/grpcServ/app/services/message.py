import json
import uuid
import grpc
from datetime import datetime, timezone
from google.protobuf.empty_pb2 import Empty
from sqlalchemy import select, func

from database import AsyncSessionLocal
from protobuf import mess_pb2, mess_pb2_grpc
from services.access_session import require_current_user_uuid
from services.enums import MemberRole, MemberStatus
from services.models import Attachment, ChatMember, Message, MessageStatus, Reaction
from services.redis_client import redis_client
from core.config import settings
from google.protobuf.timestamp_pb2 import Timestamp


PROTO_MESSAGE_TYPE_TO_DB = {
    mess_pb2.MESSAGE_TYPE_UNSPECIFIED: "text",
    mess_pb2.TEXT: "text",
    mess_pb2.IMAGE: "image",
    mess_pb2.VIDEO: "video",
    mess_pb2.AUDIO: "audio",
    mess_pb2.FILE: "file",
    mess_pb2.VOICE: "voice",
    mess_pb2.STICKER: "sticker",
    mess_pb2.LOCATION: "location",
    mess_pb2.CONTACT: "contact",
    mess_pb2.SYSTEM: "system",
}

# Обратный маппинг (строка -> protobuf enum)
DB_MESSAGE_TYPE_TO_PROTO = {v: k for k, v in PROTO_MESSAGE_TYPE_TO_DB.items()}


def _dt_to_ts(dt: datetime) -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


class MessageServicer(mess_pb2_grpc.MessageServiceServicer):
    async def _require_current_user(self, context) -> uuid.UUID:
        return await require_current_user_uuid(context)

    async def _get_message(self, session, message_id: int, chat_id: uuid.UUID = None) -> Message | None:
        stmt = select(Message).where(Message.message_id == message_id, Message.deleted_at.is_(None))
        if chat_id is not None:
            stmt = stmt.where(Message.chat_id == chat_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    def _message_to_proto(self, msg: Message, statuses: list[MessageStatus] | None = None) -> mess_pb2.Message:
        pb = mess_pb2.Message(
            message_id=msg.message_id,
            chat_id=str(msg.chat_id),
            sender_id=str(msg.sender_id),
            type=DB_MESSAGE_TYPE_TO_PROTO.get(msg.type, mess_pb2.TEXT),   # преобразуем строку в enum
            created_at=_dt_to_ts(msg.created_at),
            updated_at=_dt_to_ts(msg.updated_at),
            is_edited=msg.is_edited,
        )
        if msg.content:
            pb.content = msg.content
        if msg.reply_to_id:
            pb.reply_to_id = msg.reply_to_id
        if msg.deleted_at:
            pb.deleted_at.CopyFrom(_dt_to_ts(msg.deleted_at))

        if statuses:
            for s in statuses:
                status_pb = mess_pb2.MessageStatus(
                    message_id=s.message_id,
                    user_id=str(s.user_id),
                    message_created_at=_dt_to_ts(s.message_created_at),
                )
                if s.delivered_at:
                    status_pb.delivered_at.CopyFrom(_dt_to_ts(s.delivered_at))
                if s.read_at:
                    status_pb.read_at.CopyFrom(_dt_to_ts(s.read_at))
                pb.statuses.append(status_pb)
        return pb

    def _reaction_to_proto(self, reaction: Reaction) -> mess_pb2.Reaction:
        pb = mess_pb2.Reaction(
            message_id=reaction.message_id,
            user_id=str(reaction.user_id),
            emoji=reaction.emoji,
        )
        pb.created_at.CopyFrom(_dt_to_ts(reaction.created_at))
        return pb

    async def SendMessage(self, request, context):
        sender_uuid = await self._require_current_user(context)
        chat_uuid = uuid.UUID(request.chat_id)

        async with AsyncSessionLocal() as session:
            # Проверка членства отправителя
            res = await session.execute(
                select(ChatMember).where(
                    ChatMember.chat_id == chat_uuid,
                    ChatMember.user_id == sender_uuid,
                    ChatMember.status == MemberStatus.active,
                )
            )
            if not res.scalar_one_or_none():
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a member of this chat")

            now = datetime.now(timezone.utc)
            msg_type_str = PROTO_MESSAGE_TYPE_TO_DB.get(request.type, "text")
            msg = Message(
                chat_id=chat_uuid,
                sender_id=sender_uuid,
                content=request.content if request.HasField("content") else None,
                type=msg_type_str,
                message_metadata=dict(request.message_metadata) if request.HasField("message_metadata") else None,
                reply_to_id=request.reply_to_id if request.HasField("reply_to_id") else None,
                created_at=now,
                updated_at=now,
            )
            session.add(msg)
            await session.flush()

            for att in request.attachments:
                if att.HasField("attachment_id"):
                    attachment_id = uuid.UUID(att.attachment_id)
                    # Найти attachment и обновить его message_id и message_created_at
                    stmt = select(Attachment).where(Attachment.attachment_id == attachment_id)
                    attachment = (await session.execute(stmt)).scalar_one_or_none()
                    if attachment:
                        attachment.message_id = msg.message_id
                        attachment.message_created_at = msg.created_at
                        session.add(attachment)

            await session.commit()
            await session.refresh(msg)

            # Публикация события в Redis
            event_data = {
                "event": "message.new",
                "payload": {
                    "message_id": msg.message_id,
                    "chat_id": str(msg.chat_id),
                    "sender_id": str(msg.sender_id),
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat(),
                }
            }
            await redis_client.publish(settings.REDIS_EVENTS_CHANNEL, json.dumps(event_data))

            return self._message_to_proto(msg)

    async def GetMessage(self, request, context):
        user_uuid = await self._require_current_user(context)
        chat_uuid = uuid.UUID(request.chat_id)

        async with AsyncSessionLocal() as session:
            # Проверка членства
            res = await session.execute(
                select(ChatMember).where(
                    ChatMember.chat_id == chat_uuid,
                    ChatMember.user_id == user_uuid,
                    ChatMember.status == MemberStatus.active,
                )
            )
            if not res.scalar_one_or_none():
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a member of this chat")

            msg = await self._get_message(session, request.message_id, chat_uuid)
            if not msg:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Message not found")

            statuses_res = await session.execute(
                select(MessageStatus).where(MessageStatus.message_id == msg.message_id)
            )
            statuses = statuses_res.scalars().all()
            return self._message_to_proto(msg, statuses)

    async def ListMessages(self, request, context):
        user_uuid = await self._require_current_user(context)
        chat_uuid = uuid.UUID(request.chat_id)

        page_size = request.page_size if request.page_size > 0 else 50
        try:
            offset = int(request.page_token) if request.page_token else 0
        except ValueError:
            offset = 0

        async with AsyncSessionLocal() as session:
            # Проверка членства
            res = await session.execute(
                select(ChatMember).where(
                    ChatMember.chat_id == chat_uuid,
                    ChatMember.user_id == user_uuid,
                    ChatMember.status == MemberStatus.active,
                )
            )
            if not res.scalar_one_or_none():
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a member of this chat")

            stmt = (
                select(Message)
                .where(Message.chat_id == chat_uuid, Message.deleted_at.is_(None))
                .order_by(Message.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            messages = (await session.execute(stmt)).scalars().all()

            total_res = await session.execute(
                select(func.count()).where(Message.chat_id == chat_uuid, Message.deleted_at.is_(None))
            )
            total = total_res.scalar_one() or 0

            next_token = str(offset + page_size) if offset + page_size < total else ""
            return mess_pb2.MessagesListResponse(
                messages=[self._message_to_proto(m) for m in messages],
                next_page_token=next_token,
                total_count=total,
            )

    async def UpdateMessage(self, request, context):
        user_uuid = await self._require_current_user(context)
        chat_uuid = uuid.UUID(request.chat_id)

        async with AsyncSessionLocal() as session:
            msg = await self._get_message(session, request.message_id, chat_uuid)
            if not msg:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Message not found")
            if msg.sender_id != user_uuid:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Only sender can edit the message")

            if request.HasField("content"):
                msg.content = request.content
            msg.updated_at = datetime.now(timezone.utc)
            msg.is_edited = True

            await session.commit()
            await session.refresh(msg)

            event_data = {
                "event": "message.update",
                "payload": {
                    "message_id": msg.message_id,
                    "chat_id": str(msg.chat_id),
                    "content": msg.content,
                    "updated_at": msg.updated_at.isoformat(),
                    "is_edited": msg.is_edited,
                }
            }
            await redis_client.publish(settings.REDIS_EVENTS_CHANNEL, json.dumps(event_data))

            return self._message_to_proto(msg)

    async def DeleteMessage(self, request, context):
        user_uuid = await self._require_current_user(context)
        chat_uuid = uuid.UUID(request.chat_id)

        async with AsyncSessionLocal() as session:
            msg = await self._get_message(session, request.message_id, chat_uuid)
            if not msg:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Message not found")

            if msg.sender_id != user_uuid:
                res = await session.execute(
                    select(ChatMember).where(
                        ChatMember.chat_id == chat_uuid,
                        ChatMember.user_id == user_uuid,
                        ChatMember.status == MemberStatus.active,
                    )
                )
                member = res.scalar_one_or_none()
                if not member or member.role not in (MemberRole.admin, MemberRole.owner):
                    await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient permissions")

            msg.deleted_at = datetime.now(timezone.utc)
            await session.commit()

            event_data = {
                "event": "message.delete",
                "payload": {
                    "message_id": msg.message_id,
                    "chat_id": str(msg.chat_id),
                    "deleted_at": msg.deleted_at.isoformat(),
                }
            }
            await redis_client.publish(settings.REDIS_EVENTS_CHANNEL, json.dumps(event_data))

            return Empty()

    async def AddReaction(self, request, context):
        user_uuid = await self._require_current_user(context)
        chat_uuid = uuid.UUID(request.chat_id)

        async with AsyncSessionLocal() as session:
            # Проверка членства
            res = await session.execute(
                select(ChatMember).where(
                    ChatMember.chat_id == chat_uuid,
                    ChatMember.user_id == user_uuid,
                    ChatMember.status == MemberStatus.active,
                )
            )
            if not res.scalar_one_or_none():
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a member of this chat")

            msg = await self._get_message(session, request.message_id, chat_uuid)
            if not msg or msg.deleted_at:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Message not found")

            existing = await session.execute(
                select(Reaction).where(
                    Reaction.message_id == request.message_id,
                    Reaction.user_id == user_uuid,
                    Reaction.emoji == request.emoji,
                )
            )
            if existing.scalar_one_or_none():
                await context.abort(grpc.StatusCode.ALREADY_EXISTS, "Reaction already exists")

            reaction = Reaction(
                message_id=request.message_id,
                user_id=user_uuid,
                message_created_at=msg.created_at,
                emoji=request.emoji,
            )
            session.add(reaction)
            await session.commit()
            await session.refresh(reaction)

            event_data = {
                "event": "reaction.add",
                "payload": {
                    "message_id": reaction.message_id,
                    "chat_id": str(chat_uuid),
                    "user_id": str(user_uuid),
                    "emoji": reaction.emoji,
                    "created_at": reaction.created_at.isoformat(),
                }
            }
            await redis_client.publish(settings.REDIS_EVENTS_CHANNEL, json.dumps(event_data))

            return self._reaction_to_proto(reaction)

    async def RemoveReaction(self, request, context):
        user_uuid = await self._require_current_user(context)
        chat_uuid = uuid.UUID(request.chat_id)

        async with AsyncSessionLocal() as session:
            # Проверка членства
            res = await session.execute(
                select(ChatMember).where(
                    ChatMember.chat_id == chat_uuid,
                    ChatMember.user_id == user_uuid,
                    ChatMember.status == MemberStatus.active,
                )
            )
            if not res.scalar_one_or_none():
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a member of this chat")

            reaction_res = await session.execute(
                select(Reaction).where(
                    Reaction.message_id == request.message_id,
                    Reaction.user_id == user_uuid,
                    Reaction.emoji == request.emoji,
                )
            )
            reaction = reaction_res.scalar_one_or_none()
            if not reaction:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Reaction not found")

            await session.delete(reaction)
            await session.commit()

            event_data = {
                "event": "reaction.remove",
                "payload": {
                    "message_id": request.message_id,
                    "chat_id": str(chat_uuid),
                    "user_id": str(user_uuid),
                    "emoji": request.emoji,
                }
            }
            await redis_client.publish(settings.REDIS_EVENTS_CHANNEL, json.dumps(event_data))

            return Empty()

    async def GetMessageStatus(self, request, context):
        # Необязательный метод – можно оставить заглушку
        return mess_pb2.MessageStatusResponse()

    async def MarkAsDelivered(self, request: mess_pb2.MarkAsDeliveredRequest, context) -> Empty:
        """
        Отмечает сообщение как доставленное для текущего пользователя.
        Публикует событие status.update в Redis.
        """
        user_uuid = await require_current_user_uuid(context)
        chat_uuid = uuid.UUID(request.chat_id)

        async with AsyncSessionLocal() as session:
            # Проверка членства в чате
            member = await session.execute(
                select(ChatMember).where(
                    ChatMember.chat_id == chat_uuid,
                    ChatMember.user_id == user_uuid,
                    ChatMember.status == MemberStatus.active,
                )
            )
            if not member.scalar_one_or_none():
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a member of this chat")

            # Получаем статус сообщения
            stmt = select(MessageStatus).where(
                MessageStatus.message_id == request.message_id,
                MessageStatus.user_id == user_uuid,
            )
            status = (await session.execute(stmt)).scalar_one_or_none()
            if not status:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Message status not found")

            # Если уже доставлено – ничего не делаем
            if not status.delivered_at:
                status.delivered_at = datetime.now(timezone.utc)
                await session.commit()

                # Публикуем событие в Redis
                event_data = {
                    "event": "status.update",
                    "payload": {
                        "message_id": request.message_id,
                        "chat_id": str(chat_uuid),
                        "user_id": str(user_uuid),
                        "delivered_at": status.delivered_at.isoformat(),
                        "read_at": status.read_at.isoformat() if status.read_at else None,
                    }
                }
                await redis_client.publish(settings.REDIS_EVENTS_CHANNEL, json.dumps(event_data))

        return Empty()

    async def MarkAsRead(self, request: mess_pb2.MarkAsReadRequest, context) -> Empty:
        """
        Отмечает сообщение как прочитанное для текущего пользователя.
        Если доставка не была отмечена ранее, устанавливает delivered_at = read_at.
        Публикует событие status.update в Redis.
        """
        user_uuid = await require_current_user_uuid(context)
        chat_uuid = uuid.UUID(request.chat_id)

        async with AsyncSessionLocal() as session:
            # Проверка членства в чате
            member = await session.execute(
                select(ChatMember).where(
                    ChatMember.chat_id == chat_uuid,
                    ChatMember.user_id == user_uuid,
                    ChatMember.status == MemberStatus.active,
                )
            )
            if not member.scalar_one_or_none():
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a member of this chat")

            # Получаем статус сообщения
            stmt = select(MessageStatus).where(
                MessageStatus.message_id == request.message_id,
                MessageStatus.user_id == user_uuid,
            )
            status = (await session.execute(stmt)).scalar_one_or_none()
            if not status:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Message status not found")

            # Если уже прочитано – ничего не делаем
            if not status.read_at:
                status.read_at = datetime.now(timezone.utc)
                # Если доставка не была отмечена, ставим её тем же временем
                if not status.delivered_at:
                    status.delivered_at = status.read_at
                await session.commit()

                # Публикуем событие в Redis
                event_data = {
                    "event": "status.update",
                    "payload": {
                        "message_id": request.message_id,
                        "chat_id": str(chat_uuid),
                        "user_id": str(user_uuid),
                        "delivered_at": status.delivered_at.isoformat(),
                        "read_at": status.read_at.isoformat(),
                    }
                }
                await redis_client.publish(settings.REDIS_EVENTS_CHANNEL, json.dumps(event_data))

        return Empty()

    async def SearchMessages(self, request, context):
        user_uuid = await self._require_current_user(context)
        chat_uuid = uuid.UUID(request.chat_id)
        query = request.query
        page = max(1, request.page)
        page_size = min(100, max(1, request.page_size))
        offset = (page - 1) * page_size
        async with AsyncSessionLocal() as session:
            # Проверка членства
            res = await session.execute(
                select(ChatMember).where(
                    ChatMember.chat_id == chat_uuid,
                    ChatMember.user_id == user_uuid,
                    ChatMember.status == MemberStatus.active,
                )
            )
            if not res.scalar_one_or_none():
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a member of this chat")
            stmt = (
                select(Message)
                .where(
                    Message.chat_id == chat_uuid,
                    Message.deleted_at.is_(None),
                    Message.content.ilike(f"%{query}%")
                )
                .order_by(Message.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            messages = (await session.execute(stmt)).scalars().all()
            total_res = await session.execute(
                select(func.count()).where(
                    Message.chat_id == chat_uuid,
                    Message.deleted_at.is_(None),
                    Message.content.ilike(f"%{query}%")
                )
            )
            total = total_res.scalar_one() or 0
            return mess_pb2.MessagesListResponse(
                messages=[self._message_to_proto(m) for m in messages],
                total_count=total,
                next_page_token=str(offset + page_size) if offset + page_size < total else "",
            )