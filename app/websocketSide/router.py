from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import Select, select

from session_auth import verify_access_session
from enums import MessageType
from database import AsyncSessionLocal
from enums import MemberStatus as DbMemberStatus
from enums import MessageType as DbMessageType
from models import ChatMember, Message
from config import settings
from manager import manager
from redis_c import OfflineMessage, RedisClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws")


class MessageSendPayload(BaseModel):
    chat_id: str
    content: Optional[str] = None
    type: MessageType = MessageType.text
    message_metadata: Optional[dict] = None
    reply_to_id: Optional[int] = None
    client_message_id: Optional[str] = None


class TypingPayload(BaseModel):
    chat_id: str


class ClientEnvelope(BaseModel):
    event: Literal["message.send", "typing.start", "typing.stop", "ping"]
    payload: Optional[dict] = None


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
    if not principal:
        return None

    return principal.user_id


async def _validate_origin(websocket: WebSocket) -> bool:
    if settings.DEBUG:
        return True
    origin = websocket.headers.get("origin")
    return origin in settings.ALLOWED_ORIGINS


async def _get_chat_member_ids(chat_id: uuid.UUID) -> list[str]:
    async with AsyncSessionLocal() as db:
        stmt: Select = select(ChatMember.user_id).where(
            ChatMember.chat_id == chat_id,
            ChatMember.status == DbMemberStatus.active,
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [str(user_id) for user_id in rows]


async def _assert_user_in_chat(chat_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    async with AsyncSessionLocal() as db:
        stmt: Select = select(ChatMember.user_id).where(
            ChatMember.chat_id == chat_id,
            ChatMember.user_id == user_id,
            ChatMember.status == DbMemberStatus.active,
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        return row is not None


async def _persist_message(chat_id: uuid.UUID, sender_id: uuid.UUID, payload: MessageSendPayload) -> Message:
    async with AsyncSessionLocal() as db:
        message = Message(
            chat_id=chat_id,
            sender_id=sender_id,
            content=payload.content,
            type=DbMessageType(payload.type.value),
            message_metadata=payload.message_metadata,
            reply_to_id=payload.reply_to_id,
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
        return message


@router.websocket("/chat")
@router.websocket("/chat/{requested_user_id}")
async def websocket_chat_endpoint(websocket: WebSocket, requested_user_id: Optional[str] = None):
    if not await _validate_origin(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    current_user_id_raw = await _resolve_user_id_from_token(websocket)
    if not current_user_id_raw:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing, invalid or revoked access token")
        return

    if requested_user_id and requested_user_id != current_user_id_raw:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User mismatch")
        return

    try:
        current_user_id = uuid.UUID(current_user_id_raw)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid user id in token")
        return

    redis_client: RedisClient = websocket.app.state.redis_client
    connection = await manager.connect(websocket, str(current_user_id))
    await redis_client.add_online_user(str(current_user_id))

    try:
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

            if envelope.event == "ping":
                await websocket.send_json({"event": "pong", "server_time": datetime.now(timezone.utc).isoformat()})
                continue

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

    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(connection)
        await redis_client.remove_online_user(str(current_user_id))