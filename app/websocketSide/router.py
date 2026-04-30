# app/websocketSide/router.py

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import grpc
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from config import settings
from database import AsyncSessionLocal
from enums import MemberStatus as DbMemberStatus, MessageType as DbMessageType
from manager import manager
from models import ChatMember, Message
from protobuf import mess_pb2, mess_pb2_grpc
from redis_c import OfflineMessage, RedisClient
from session_auth import verify_access_session

from sqlalchemy import select
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws")


class MessageSendPayload(BaseModel):
    chat_id: str
    content: Optional[str] = None
    type: str = "text"          # можно завести Enum, но для простоты строка
    message_metadata: Optional[dict] = None
    reply_to_id: Optional[int] = None
    client_message_id: Optional[str] = None


class TypingPayload(BaseModel):
    chat_id: str


class ClientEnvelope(BaseModel):
    event: str  # не ограничиваем строго, чтобы не падать при неизвестных
    payload: Optional[dict] = None


def _extract_access_token(websocket: WebSocket) -> Optional[str]:
    """Извлекает access‑токен из заголовка или query параметров."""
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
    """Проверяет токен через Redis и возвращает user_id."""
    token = _extract_access_token(websocket)
    if not token:
        return None
    principal = await verify_access_session(token)
    if not principal:
        return None
    return principal.user_id


async def _validate_origin(websocket: WebSocket) -> bool:
    if settings.DEBUG:
        return True
    origin = websocket.headers.get("origin")
    return origin in settings.ALLOWED_ORIGINS


async def _get_chat_member_ids(chat_id: uuid.UUID) -> list[str]:
    """Возвращает список user_id активных участников чата."""
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(ChatMember.user_id).where(
                    ChatMember.chat_id == chat_id,
                    ChatMember.status == DbMemberStatus.active,
                )
            )
        ).scalars().all()
        return [str(uid) for uid in rows]


async def _assert_user_in_chat(chat_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Проверяет, состоит ли пользователь в чате."""
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(ChatMember.user_id).where(
                    ChatMember.chat_id == chat_id,
                    ChatMember.user_id == user_id,
                    ChatMember.status == DbMemberStatus.active,
                )
            )
        ).scalar_one_or_none()
        return row is not None


@router.websocket("/chat")
@router.websocket("/chat/{requested_user_id}")
async def websocket_chat_endpoint(websocket: WebSocket, requested_user_id: Optional[str] = None):
    if not await _validate_origin(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    current_user_id_raw = await _resolve_user_id_from_token(websocket)
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

    # Сохраняем токен для последующих gRPC-вызовов
    access_token = _extract_access_token(websocket)
    if not access_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Access token required")
        return

    redis_client: RedisClient = websocket.app.state.redis_client
    connection = await manager.connect(websocket, str(current_user_id))
    await redis_client.add_online_user(str(current_user_id))

    try:
        # Доставляем накопленные офлайн‑сообщения
        offline_messages = await redis_client.dequeue_all_offline_messages(str(current_user_id))
        for item in offline_messages:
            await manager.send_to_user(str(current_user_id), item.payload)

        while True:
            raw = await websocket.receive_json()
            try:
                envelope = ClientEnvelope.model_validate(raw)
            except ValidationError as exc:
                await websocket.send_json({"event": "error", "detail": exc.errors()})
                continue

            # Обработка ping
            if envelope.event == "ping":
                await websocket.send_json({
                    "event": "pong",
                    "server_time": datetime.now(timezone.utc).isoformat(),
                })
                continue

            # Обработка typing-событий
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

            # Обработка отправки сообщения
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

                # gRPC-клиент SendMessage
                stub: mess_pb2_grpc.MessageServiceStub = websocket.app.state.message_stub
                metadata = (("authorization", f"Bearer {access_token}"),)

                # Формируем и отправляем запрос
                grpc_request = mess_pb2.SendMessageRequest(
                    chat_id=str(chat_uuid),
                    sender_id=str(current_user_id),
                    content=payload.content or "",
                    type=mess_pb2.TEXT,  # в MVP только текст, позже расширить
                )
                if payload.reply_to_id:
                    grpc_request.reply_to_id = payload.reply_to_id
                # вложения и упоминания можно добавить аналогично

                try:
                    loop = asyncio.get_running_loop()
                    grpc_response = await loop.run_in_executor(
                        None,
                        lambda: stub.SendMessage(grpc_request, timeout=5, metadata=metadata)
                    )
                except grpc.RpcError as e:
                    await websocket.send_json({
                        "event": "error",
                        "detail": f"Failed to send message: {e.details()}",
                    })
                    continue

                # Формируем payload для рассылки по WebSocket
                delivered_payload = {
    "event": "message.new",
    "payload": {
        "message_id": grpc_response.message_id,
        "chat_id": str(grpc_response.chat_id),
        "sender_id": str(grpc_response.sender_id),
        "content": grpc_response.content,
        "created_at": grpc_response.created_at.ToDatetime().isoformat(),
        "type": "text",
        "reply_to_id": grpc_response.reply_to_id if grpc_response.HasField("reply_to_id") else None,
    }
}

                # Рассылаем всем активным участникам чата (включая отправителя)
                member_ids = await _get_chat_member_ids(chat_uuid)
                await manager.send_to_users(member_ids, delivered_payload)

                # Для офлайн‑пользователей кладём в очередь Redis
                for user_id in member_ids:
                    if not await redis_client.is_user_online(user_id):
                        offline_msg = OfflineMessage(
                            sender_id=str(current_user_id),
                            recipient_id=user_id,
                            payload=delivered_payload["payload"],
                        )
                        await redis_client.enqueue_offline_message(offline_msg)

                continue

            # Неизвестное событие
            await websocket.send_json({
                "event": "error",
                "detail": f"Unknown event: {envelope.event}",
            })

    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(connection)
        await redis_client.remove_online_user(str(current_user_id))