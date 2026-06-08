from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import grpc
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import select, update

from config import settings
from database import AsyncSessionLocal
from enums import MemberStatus as DbMemberStatus
from manager import manager
from models import ChatMember, User
from protobuf import mess_pb2, mess_pb2_grpc
from redis_c import OfflineMessage, RedisClient
from session_auth import verify_access_session
from functools import lru_cache
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws")
_last_seen_cache = {} 

HEARTBEAT_TIMEOUT = 60

async def update_user_last_seen(user_id: uuid.UUID, force: bool = False) -> None:
    """Обновляет last_seen пользователя в БД, но не чаще раза в 30 секунд."""
    now = datetime.now(timezone.utc)
    last = _last_seen_cache.get(user_id)
    if not force and last and (now - last).total_seconds() < 30:
        return
    _last_seen_cache[user_id] = now
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(User).where(User.user_id == user_id).values(last_seen=now)
        )
        await session.commit()
# ---------- Pydantic модели ----------
class MessageAckPayload(BaseModel):
    message_id: int
    chat_id: str

class MessageSendPayload(BaseModel):
    chat_id: str
    content: Optional[str] = None
    type: str = "text"
    message_metadata: Optional[dict] = None
    reply_to_id: Optional[int] = None
    client_message_id: Optional[str] = None

class TypingPayload(BaseModel):
    chat_id: str

class ClientEnvelope(BaseModel):
    event: str
    payload: Optional[dict] = None

_chat_members_cache = {}
_cache_ttl = timedelta(seconds=5)


async def _get_chat_member_ids(chat_id: uuid.UUID) -> list[str]:
    now = datetime.now(timezone.utc)
    cache_key = str(chat_id)
    if cache_key in _chat_members_cache:
        cached_time, members = _chat_members_cache[cache_key]
        if now - cached_time < _cache_ttl:
            return members
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(ChatMember.user_id).where(
                ChatMember.chat_id == chat_id,
                ChatMember.status == DbMemberStatus.active,
            )
        )
        members = [str(uid) for uid in rows.scalars().all()]
        _chat_members_cache[cache_key] = (now, members)
        return members

async def _assert_user_in_chat(chat_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    async with AsyncSessionLocal() as db:
        row = await db.execute(
            select(ChatMember.user_id).where(
                ChatMember.chat_id == chat_id,
                ChatMember.user_id == user_id,
                ChatMember.status == DbMemberStatus.active,
            )
        )
        return row.scalar_one_or_none() is not None

def _extract_access_token(websocket: WebSocket) -> Optional[str]:
    auth_header = websocket.headers.get("authorization")
    if auth_header:
        lower = auth_header.lower()
        if lower.startswith("bearer "):
            return auth_header[7:].strip()
        return auth_header.strip()
    for key in ("access_token", "token"):
        token = websocket.query_params.get(key)
        if token:
            return token.strip()
    return None

async def _resolve_user_id_from_token(websocket: WebSocket) -> Optional[str]:
    token = _extract_access_token(websocket)
    if not token:
        return None
    principal = await verify_access_session(token)
    return principal.user_id if principal else None

async def _validate_origin(websocket: WebSocket) -> bool:
    if settings.DEBUG:
        return True
    origin = websocket.headers.get("origin")
    return origin in settings.ALLOWED_ORIGINS

async def handle_redis_event(app, raw_data: str):
    try:
        data = json.loads(raw_data)
        event_type = data.get("event")
        payload = data.get("payload", {})
        chat_id = payload.get("chat_id")

        # Событие изменения онлайн-статуса пользователя (без chat_id)
        if event_type == "user.online":
            user_id = payload.get("user_id")
            if user_id:
                # Отправляем только тому пользователю, чей статус изменился
                await manager.send_to_user(user_id, {"event": event_type, "payload": payload})
            return

        # Для событий с chat_id – рассылка участникам чата
        if not chat_id:
            logger.warning("Redis event without chat_id: %s", data)
            return
        chat_uuid = uuid.UUID(chat_id)
        members = await _get_chat_member_ids(chat_uuid)
        logger.info(f"📢 Event '{event_type}' for chat {chat_id}, members: {members}")
        redis_client: RedisClient = app.state.redis_client
        for user_id in members:
            is_online = await redis_client.is_user_online(user_id)
            logger.debug(f"User {user_id} online: {is_online}")
            if is_online:
                await manager.send_to_user(user_id, {"event": event_type, "payload": payload})
            else:
                offline_msg = OfflineMessage(
                    event_type=event_type,
                    payload=payload,
                    chat_id=chat_id,
                    recipient_id=user_id,
                )
                await redis_client.enqueue_offline_message(offline_msg)
    except Exception as e:
        logger.error(f"Failed to process redis event: {e}", exc_info=True)


# ---------- WebSocket эндпоинт ----------
@router.websocket("/chat")
@router.websocket("/chat/{requested_user_id}")
async def websocket_chat_endpoint(websocket: WebSocket, requested_user_id: Optional[str] = None):
    # 1. Проверка origin
    if not await _validate_origin(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Извлечение user_id из токена
    current_user_id_raw = await _resolve_user_id_from_token(websocket)
    logger.info(f"Websocket connection attempt for user {current_user_id_raw}")
    if not current_user_id_raw:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing or invalid access token")
        return

    if requested_user_id and requested_user_id != current_user_id_raw:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User mismatch")
        return

    try:
        current_user_id = uuid.UUID(current_user_id_raw)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid user id in token")
        return

    access_token = _extract_access_token(websocket)
    if not access_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Access token required")
        return

    redis_client: RedisClient = websocket.app.state.redis_client
    if redis_client is None:
        logger.error("Redis client not initialized")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Internal server error")
        return

    # 3. Принимаем соединение и регистрируем в менеджере
    connection = await manager.connect(websocket, str(current_user_id))
    await update_user_last_seen(current_user_id, force=True)

    # 4. Добавляем пользователя в онлайн-множество Redis
    try:
        await redis_client.add_online_user(str(current_user_id))
        logger.info(f"✅ User {current_user_id} marked online in Redis")
    except Exception as e:
        logger.error(f"Failed to add online user: {e}", exc_info=True)
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    # 5. Публикуем событие "пользователь онлайн"
    await redis_client.publish(
        "messenger:events",
        json.dumps({
            "event": "user.online",
            "payload": {"user_id": str(current_user_id), "is_online": True}
        })
    )

    # 6. Отправляем накопившиеся offline-сообщения (если есть)
    try:
        offline_messages = await redis_client.dequeue_all_offline_messages(str(current_user_id))
        for msg in offline_messages:
            await websocket.send_json({"event": msg.event_type, "payload": msg.payload})
    except Exception as e:
        logger.error(f"Failed to process offline messages: {e}", exc_info=True)
        # Не закрываем соединение, продолжаем

    # 7. Heartbeat (проверка ping/pong)
    last_ping_time = datetime.now(timezone.utc)

    async def heartbeat_checker():
        nonlocal last_ping_time
        while True:
            await asyncio.sleep(30)
            if (datetime.now(timezone.utc) - last_ping_time).total_seconds() > HEARTBEAT_TIMEOUT:
                logger.info(f"Heartbeat timeout for user {current_user_id}")
                await websocket.close(code=status.WS_1000_NORMAL_CLOSURE, reason="Heartbeat timeout")
                break

    heartbeat_task = asyncio.create_task(heartbeat_checker())

    try:
        # 8. Основной цикл обработки сообщений от клиента
        while True:
            raw = await websocket.receive_json()
            await update_user_last_seen(current_user_id)
            try:
                envelope = ClientEnvelope.model_validate(raw)
            except ValidationError as exc:
                await websocket.send_json({"event": "error", "detail": exc.errors()})
                continue

            # --- Ping ---
            if envelope.event == "ping":
                last_ping_time = datetime.now(timezone.utc)
                await websocket.send_json({"event": "pong", "server_time": last_ping_time.isoformat()})
                continue

            # --- Typing start / stop ---
            if envelope.event in {"typing.start", "typing.stop"}:
                try:
                    payload = TypingPayload.model_validate(envelope.payload or {})
                    chat_uuid = uuid.UUID(payload.chat_id)
                except (ValidationError, ValueError) as exc:
                    await websocket.send_json({"event": "error", "detail": str(exc)})
                    continue

                if not await _assert_user_in_chat(chat_uuid, current_user_id):
                    await websocket.send_json({"event": "error", "detail": "Access denied for chat"})
                    continue

                members = await _get_chat_member_ids(chat_uuid)
                await manager.send_to_users(
                    members,
                    {
                        "event": envelope.event,
                        "payload": {
                            "chat_id": str(chat_uuid),
                            "user_id": str(current_user_id),
                            "at": datetime.now(timezone.utc).isoformat(),
                        },
                    },
                    exclude_user_id=str(current_user_id),
                )
                continue

            # --- Отправка сообщения ---
            if envelope.event == "message.send":
                try:
                    payload = MessageSendPayload.model_validate(envelope.payload or {})
                    chat_uuid = uuid.UUID(payload.chat_id)
                except (ValidationError, ValueError) as exc:
                    await websocket.send_json({"event": "error", "detail": str(exc)})
                    continue

                if not await _assert_user_in_chat(chat_uuid, current_user_id):
                    await websocket.send_json({"event": "error", "detail": "Access denied for chat"})
                    continue

                stub: mess_pb2_grpc.MessageServiceStub = websocket.app.state.message_stub
                metadata = (("authorization", f"Bearer {access_token}"),)

                grpc_request = mess_pb2.SendMessageRequest(
                    chat_id=str(chat_uuid),
                    sender_id=str(current_user_id),
                    content=payload.content or "",
                    type=mess_pb2.TEXT,
                )
                if payload.reply_to_id:
                    grpc_request.reply_to_id = payload.reply_to_id

                try:
                    loop = asyncio.get_running_loop()
                    grpc_response = await loop.run_in_executor(
                        None,
                        lambda: stub.SendMessage(grpc_request, timeout=5, metadata=metadata)
                    )
                    # Опционально: подтверждение клиенту
                    # await websocket.send_json({"event": "message.sent", "payload": {"message_id": grpc_response.message_id}})
                except grpc.RpcError as e:
                    await websocket.send_json({
                        "event": "error",
                        "detail": f"Failed to send message: {e.details()}",
                    })
                continue

            # --- Подтверждение доставки (ack) ---
            if envelope.event == "message.ack":
                try:
                    payload = MessageAckPayload.model_validate(envelope.payload or {})
                    stub: mess_pb2_grpc.MessageServiceStub = websocket.app.state.message_stub
                    metadata = (("authorization", f"Bearer {access_token}"),)
                    grpc_request = mess_pb2.MarkAsDeliveredRequest(
                        message_id=payload.message_id,
                        chat_id=payload.chat_id,
                    )
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: stub.MarkAsDelivered(grpc_request, timeout=5, metadata=metadata)
                    )
                except Exception as e:
                    logger.error(f"Failed to process message.ack: {e}")
                continue

            if envelope.event == "call.start":
            # Проксируем в gRPC CallService
                try:
                    payload = envelope.payload or {}
                    chat_id = payload.get("chat_id")
                    call_type = payload.get("type", "video")
                    if not chat_id:
                        await websocket.send_json({"event": "error", "detail": "chat_id required"})
                        continue
                    stub: mess_pb2_grpc.CallServiceStub = websocket.app.state.call_stub
                    metadata = (("authorization", f"Bearer {access_token}"),)
                    grpc_req = mess_pb2.StartCallRequest(chat_id=chat_id, type=call_type)
                    resp = await loop.run_in_executor(None, lambda: stub.StartCall(grpc_req, metadata=metadata))
                    await websocket.send_json({
                        "event": "call.started",
                        "payload": {
                            "call_id": resp.call_id,
                            "token": getattr(resp, "token", None),
                            "ws_url": getattr(resp, "ws_url", None)
                        }
                    })
                except Exception as e:
                    await websocket.send_json({"event": "error", "detail": str(e)})
                continue

            if envelope.event == "call.accept":
                try:
                    call_id = envelope.payload.get("call_id")
                    if not call_id:
                        await websocket.send_json({"event": "error", "detail": "call_id required"})
                        continue
                    stub = websocket.app.state.call_stub
                    metadata = (("authorization", f"Bearer {access_token}"),)
                    grpc_req = mess_pb2.AcceptCallRequest(call_id=call_id)
                    resp = await loop.run_in_executor(None, lambda: stub.AcceptCall(grpc_req, metadata=metadata))
                    await websocket.send_json({
                        "event": "call.accepted",
                        "payload": {"call_id": call_id, "token": getattr(resp, "token", None), "ws_url": getattr(resp, "ws_url", None)}
                    })
                except Exception as e:
                    await websocket.send_json({"event": "error", "detail": str(e)})
                continue

            if envelope.event == "call.reject":
                try:
                    call_id = envelope.payload.get("call_id")
                    if not call_id:
                        continue
                    stub = websocket.app.state.call_stub
                    metadata = (("authorization", f"Bearer {access_token}"),)
                    grpc_req = mess_pb2.RejectCallRequest(call_id=call_id)
                    await loop.run_in_executor(None, lambda: stub.RejectCall(grpc_req, metadata=metadata))
                except Exception as e:
                    logger.error(f"Call reject error: {e}")
                continue

            if envelope.event == "call.end":
                try:
                    call_id = envelope.payload.get("call_id")
                    if not call_id:
                        continue
                    stub = websocket.app.state.call_stub
                    metadata = (("authorization", f"Bearer {access_token}"),)
                    grpc_req = mess_pb2.EndCallRequest(call_id=call_id)
                    await loop.run_in_executor(None, lambda: stub.EndCall(grpc_req, metadata=metadata))
                except Exception as e:
                    logger.error(f"Call end error: {e}")
                continue

            # --- Неизвестное событие ---
            await websocket.send_json({
                "event": "error",
                "detail": f"Unknown event: {envelope.event}",
            })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {current_user_id}")
    except Exception as e:
        logger.error(f"Unexpected error in websocket loop: {e}", exc_info=True)
    finally:
        heartbeat_task.cancel()
        await manager.disconnect(connection)
        # Удаляем пользователя из онлайн-множества
        await update_user_last_seen(current_user_id, force=True)
        try:
            await redis_client.remove_online_user(str(current_user_id))
            await redis_client.publish(
                "messenger:events",
                json.dumps({
                    "event": "user.online",
                    "payload": {"user_id": str(current_user_id), "is_online": False}
                })
            )
            logger.info(f"User {current_user_id} removed from online set")
        except Exception as e:
            logger.error(f"Failed to remove online user: {e}", exc_info=True)