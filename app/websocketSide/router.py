from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import grpc
import redis.asyncio as redis
from anyio import to_thread
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt
from pydantic import BaseModel, ValidationError
from sqlalchemy import select, update

from config import settings
from database import AsyncSessionLocal
from enums import MemberStatus as DbMemberStatus
from manager import manager
from models import ChatMembers as ChatMember, Users as User
from protobuf import mess_pb2, mess_pb2_grpc
from redis_c import OfflineMessage, RedisClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws")

_last_seen_cache: dict[uuid.UUID, datetime] = {}
_chat_members_cache: dict[str, tuple[datetime, list[str]]] = {}
_cache_ttl = timedelta(seconds=5)

HEARTBEAT_TIMEOUT = 60

_auth_redis_client: Optional[redis.Redis] = None


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


def _get_auth_redis() -> redis.Redis:
    global _auth_redis_client
    if _auth_redis_client is None:
        _auth_redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _auth_redis_client


def _session_key(session_id: str) -> str:
    return f"{settings.REDIS_PREFIX}:auth:session:{session_id}"


def _mask_token(token: str | None, head: int = 16, tail: int = 8) -> str:
    if not token:
        return "<empty>"
    if len(token) <= head + tail:
        return token
    return f"{token[:head]}...{token[-tail:]}"


def _get_client_desc(websocket: WebSocket) -> str:
    if websocket.client:
        return f"{websocket.client.host}:{websocket.client.port}"
    return "<unknown>"


def _get_origin(websocket: WebSocket) -> str:
    return websocket.headers.get("origin", "<missing>")


def _get_state_attr(state: Any, *names: str) -> Any:
    for name in names:
        if hasattr(state, name):
            return getattr(state, name)
    return None


async def _close_ws(
    websocket: WebSocket,
    code: int,
    reason: str,
    *,
    log_level: str = "warning",
    extra: Optional[dict] = None,
) -> None:
    log_data = {
        "client": _get_client_desc(websocket),
        "path": str(websocket.url),
        "origin": _get_origin(websocket),
        "reason": reason,
    }
    if extra:
        log_data.update(extra)

    log_message = "WS close before/after accept: %s"
    if log_level == "error":
        logger.error(log_message, log_data)
    elif log_level == "info":
        logger.info(log_message, log_data)
    else:
        logger.warning(log_message, log_data)

    await websocket.close(code=code, reason=reason)


async def update_user_last_seen(user_id: uuid.UUID, force: bool = False) -> None:
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

    for key in ("access_token", "accesstoken", "token"):
        token = websocket.query_params.get(key)
        if token:
            return token.strip()

    return None


async def _validate_origin_detailed(websocket: WebSocket) -> tuple[bool, str]:
    if settings.DEBUG:
        return True, "debug_enabled"

    origin = websocket.headers.get("origin")
    if not origin:
        return False, "origin_missing"

    if origin not in settings.ALLOWED_ORIGINS:
        return False, "origin_not_allowed"

    return True, "ok"


async def _verify_access_session_detailed(token: str) -> dict[str, Any]:
    if not token:
        return {"ok": False, "reason": "token_missing"}

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
    except JWTError as exc:
        logger.warning("WS auth failed: jwt_invalid error=%s", str(exc))
        return {"ok": False, "reason": "jwt_invalid"}
    except Exception as exc:
        logger.error("WS auth failed: jwt_decode_error error=%s", str(exc), exc_info=True)
        return {"ok": False, "reason": "jwt_decode_error"}

    if payload.get("type") != "access":
        logger.warning("WS auth failed: wrong_token_type type=%s", payload.get("type"))
        return {"ok": False, "reason": "wrong_token_type"}

    user_id = payload.get("sub")
    session_id = payload.get("sid")

    if not user_id or not session_id:
        logger.warning(
            "WS auth failed: missing_claims sub=%s sid=%s",
            user_id,
            session_id,
        )
        return {"ok": False, "reason": "missing_claims"}

    redis_key = _session_key(str(session_id))

    try:
        session_data = await _get_auth_redis().hgetall(redis_key)
    except Exception as exc:
        logger.error(
            "WS auth failed: redis_error key=%s error=%s",
            redis_key,
            str(exc),
            exc_info=True,
        )
        return {"ok": False, "reason": "redis_error"}

    if not session_data:
        logger.warning(
            "WS auth failed: session_not_found key=%s sub=%s sid=%s",
            redis_key,
            user_id,
            session_id,
        )
        return {"ok": False, "reason": "session_not_found"}

    stored_user_id = session_data.get("user_id") or session_data.get("userid")
    if stored_user_id != str(user_id):
        logger.warning(
            "WS auth failed: session_user_mismatch token_sub=%s redis_user_id=%s sid=%s",
            user_id,
            stored_user_id,
            session_id,
        )
        return {"ok": False, "reason": "session_user_mismatch"}

    stored_access_token = (
        session_data.get("access_token")
        or session_data.get("accesstoken")
        or session_data.get("accessToken")
    )
    if stored_access_token and stored_access_token != token:
        logger.warning(
            "WS auth failed: access_token_mismatch sid=%s token=%s redis_token=%s",
            session_id,
            _mask_token(token),
            _mask_token(stored_access_token),
        )
        return {"ok": False, "reason": "access_token_mismatch"}

    return {
        "ok": True,
        "reason": "ok",
        "user_id": str(user_id),
        "session_id": str(session_id),
        "payload": payload,
    }


async def _resolve_user_id_from_token_detailed(
    websocket: WebSocket,
) -> tuple[Optional[str], str]:
    token = _extract_access_token(websocket)
    if not token:
        return None, "token_missing"

    result = await _verify_access_session_detailed(token)
    if not result["ok"]:
        return None, result["reason"]

    return str(result["user_id"]), "ok"


def _message_type_to_proto(message_type: str | None) -> int:
    normalized = (message_type or "text").upper()
    return getattr(mess_pb2, normalized, getattr(mess_pb2, "TEXT", 0))


async def handle_redis_event(app: Any, raw_data: str) -> None:
    logger.info("Redis event received: %s", raw_data)

    try:
        data = json.loads(raw_data)
        event_type = data.get("event")
        payload = data.get("payload", {}) or {}

        if event_type == "user.online":
            user_id = payload.get("user_id") or payload.get("userid")
            if user_id:
                await manager.send_to_user(user_id, {"event": event_type, "payload": payload})
            return

        chat_id = payload.get("chat_id") or payload.get("chatid")
        if not chat_id:
            logger.warning("Redis event without chat_id: %s", data)
            return

        try:
            chat_uuid = uuid.UUID(chat_id)
        except ValueError:
            logger.warning("Redis event with invalid chat_id: %s", chat_id)
            return

        redis_client: RedisClient | None = _get_state_attr(
            app.state,
            "redis_client",
            "redisclient",
        )
        if redis_client is None:
            logger.error("Redis client missing in app.state")
            return

        members = await _get_chat_member_ids(chat_uuid)
        for user_id in members:
            is_online = await redis_client.is_user_online(user_id)
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

    except Exception as exc:
        logger.error("Failed to process redis event: %s", str(exc), exc_info=True)


@router.websocket("/chat")
@router.websocket("/chat/")
@router.websocket("/chat/{requested_user_id}")
@router.websocket("/chat/{requested_user_id}/")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    requested_user_id: Optional[str] = None,
) -> None:
    client = _get_client_desc(websocket)
    origin = _get_origin(websocket)
    token = _extract_access_token(websocket)

    origin_ok, origin_reason = await _validate_origin_detailed(websocket)
    if not origin_ok:
        await _close_ws(
            websocket,
            code=status.WS_1008_POLICY_VIOLATION,
            reason=f"Origin rejected: {origin_reason}",
            extra={
                "debug": settings.DEBUG,
                "allowed_origins": settings.ALLOWED_ORIGINS,
            },
        )
        return

    current_user_id_raw, auth_reason = await _resolve_user_id_from_token_detailed(websocket)
    if not current_user_id_raw:
        await _close_ws(
            websocket,
            code=status.WS_1008_POLICY_VIOLATION,
            reason=f"Auth rejected: {auth_reason}",
            extra={"token": _mask_token(token)},
        )
        return

    if requested_user_id and requested_user_id != current_user_id_raw:
        await _close_ws(
            websocket,
            code=status.WS_1008_POLICY_VIOLATION,
            reason="User mismatch",
            extra={
                "requested_user_id": requested_user_id,
                "token_user_id": current_user_id_raw,
            },
        )
        return

    try:
        current_user_id = uuid.UUID(current_user_id_raw)
    except ValueError:
        await _close_ws(
            websocket,
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid user id in token",
            extra={"token_user_id": current_user_id_raw},
        )
        return

    access_token = _extract_access_token(websocket)
    if not access_token:
        await _close_ws(
            websocket,
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Access token required",
        )
        return

    redis_client: RedisClient | None = _get_state_attr(
        websocket.app.state,
        "redis_client",
        "redisclient",
    )
    if redis_client is None:
        await _close_ws(
            websocket,
            code=status.WS_1011_INTERNAL_ERROR,
            reason="Redis client is not initialized",
            log_level="error",
        )
        return

    message_stub: mess_pb2_grpc.MessageServiceStub | None = _get_state_attr(
        websocket.app.state,
        "message_stub",
        "messagestub",
    )
    call_stub: mess_pb2_grpc.CallServiceStub | None = _get_state_attr(
        websocket.app.state,
        "call_stub",
        "callstub",
    )

    logger.info(
        "WS accepted: client=%s user_id=%s origin=%s path=%s",
        client,
        str(current_user_id),
        origin,
        str(websocket.url),
    )

    connection = await manager.connect(websocket, str(current_user_id))
    heartbeat_task: asyncio.Task | None = None

    try:
        await update_user_last_seen(current_user_id, force=True)

        await redis_client.add_online_user(str(current_user_id))
        await redis_client.publish(
            settings.REDIS_EVENTS_CHANNEL,
            json.dumps(
                {
                    "event": "user.online",
                    "payload": {
                        "user_id": str(current_user_id),
                        "is_online": True,
                    },
                }
            ),
        )

        try:
            offline_messages = await redis_client.dequeue_all_offline_messages(
                str(current_user_id)
            )
            for msg in offline_messages:
                await websocket.send_json(
                    {
                        "event": msg.event_type,
                        "payload": msg.payload,
                    }
                )
        except Exception as exc:
            logger.error(
                "Failed to process offline messages for user=%s error=%s",
                str(current_user_id),
                str(exc),
                exc_info=True,
            )

        last_ping_time = datetime.now(timezone.utc)

        async def heartbeat_checker() -> None:
            nonlocal last_ping_time

            while True:
                await asyncio.sleep(30)
                if (datetime.now(timezone.utc) - last_ping_time).total_seconds() > HEARTBEAT_TIMEOUT:
                    logger.info("Heartbeat timeout for user %s", str(current_user_id))
                    await websocket.close(
                        code=status.WS_1000_NORMAL_CLOSURE,
                        reason="Heartbeat timeout",
                    )
                    break

        heartbeat_task = asyncio.create_task(heartbeat_checker())

        while True:
            raw = await websocket.receive_json()
            await update_user_last_seen(current_user_id)

            try:
                envelope = ClientEnvelope.model_validate(raw)
            except ValidationError as exc:
                await websocket.send_json({"event": "error", "detail": exc.errors()})
                continue

            if envelope.event == "ping":
                last_ping_time = datetime.now(timezone.utc)
                await websocket.send_json(
                    {
                        "event": "pong",
                        "server_time": last_ping_time.isoformat(),
                    }
                )
                continue

            if envelope.event in {"typing.start", "typing.stop"}:
                try:
                    payload = TypingPayload.model_validate(envelope.payload or {})
                    chat_uuid = uuid.UUID(payload.chat_id)
                except (ValidationError, ValueError) as exc:
                    await websocket.send_json({"event": "error", "detail": str(exc)})
                    continue

                if not await _assert_user_in_chat(chat_uuid, current_user_id):
                    await websocket.send_json(
                        {"event": "error", "detail": "Access denied for chat"}
                    )
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

            if envelope.event == "message.send":
                try:
                    payload = MessageSendPayload.model_validate(envelope.payload or {})
                    chat_uuid = uuid.UUID(payload.chat_id)
                except (ValidationError, ValueError) as exc:
                    await websocket.send_json({"event": "error", "detail": str(exc)})
                    continue

                if not await _assert_user_in_chat(chat_uuid, current_user_id):
                    await websocket.send_json(
                        {"event": "error", "detail": "Access denied for chat"}
                    )
                    continue

                if message_stub is None:
                    await websocket.send_json(
                        {"event": "error", "detail": "Message service unavailable"}
                    )
                    continue

                metadata = (("authorization", f"Bearer {access_token}"),)

                grpc_request = mess_pb2.SendMessageRequest(
                    chat_id=str(chat_uuid),
                    sender_id=str(current_user_id),
                    content=payload.content or "",
                    type=_message_type_to_proto(payload.type),
                )

                if payload.reply_to_id is not None and hasattr(grpc_request, "reply_to_id"):
                    grpc_request.reply_to_id = payload.reply_to_id

                try:
                    grpc_response = await to_thread.run_sync(
                        lambda: message_stub.SendMessage(
                            grpc_request,
                            timeout=5,
                            metadata=metadata,
                        )
                    )

                    response_payload = {
                        "message_id": getattr(grpc_response, "message_id", None),
                        "chat_id": getattr(grpc_response, "chat_id", str(chat_uuid)),
                        "created_at": getattr(grpc_response, "created_at", None),
                        "client_message_id": payload.client_message_id,
                    }
                    await websocket.send_json(
                        {
                            "event": "message.sent",
                            "payload": response_payload,
                        }
                    )
                except grpc.RpcError as exc:
                    await websocket.send_json(
                        {
                            "event": "error",
                            "detail": f"Failed to send message: {exc.details()}",
                        }
                    )
                continue

            if envelope.event == "message.ack":
                try:
                    payload = MessageAckPayload.model_validate(envelope.payload or {})
                    if message_stub is None:
                        await websocket.send_json(
                            {"event": "error", "detail": "Message service unavailable"}
                        )
                        continue

                    metadata = (("authorization", f"Bearer {access_token}"),)
                    grpc_request = mess_pb2.MarkAsDeliveredRequest(
                        message_id=payload.message_id,
                        chat_id=payload.chat_id,
                    )
                    await to_thread.run_sync(
                        lambda: message_stub.MarkAsDelivered(
                            grpc_request,
                            timeout=5,
                            metadata=metadata,
                        )
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to process message.ack for user=%s error=%s",
                        str(current_user_id),
                        str(exc),
                        exc_info=True,
                    )
                continue

            if envelope.event == "call.start":
                try:
                    payload = envelope.payload or {}
                    chat_id = payload.get("chat_id")
                    call_type = payload.get("type", "video")

                    if not chat_id:
                        await websocket.send_json(
                            {"event": "error", "detail": "chat_id required"}
                        )
                        continue

                    chat_uuid = uuid.UUID(chat_id)
                    if not await _assert_user_in_chat(chat_uuid, current_user_id):
                        await websocket.send_json(
                            {"event": "error", "detail": "Access denied for chat"}
                        )
                        continue

                    if call_stub is None:
                        await websocket.send_json(
                            {"event": "error", "detail": "Call service unavailable"}
                        )
                        continue

                    metadata = (("authorization", f"Bearer {access_token}"),)
                    grpc_request = mess_pb2.StartCallRequest(
                        chat_id=str(chat_uuid),
                        type=call_type,
                    )
                    resp = await to_thread.run_sync(
                        lambda: call_stub.StartCall(grpc_request, metadata=metadata)
                    )

                    await websocket.send_json(
                        {
                            "event": "call.started",
                            "payload": {
                                "call_id": resp.call_id,
                                "token": getattr(resp, "token", None),
                                "ws_url": getattr(resp, "ws_url", None),
                            },
                        }
                    )
                except grpc.RpcError as exc:
                    await websocket.send_json(
                        {"event": "error", "detail": exc.details() or str(exc)}
                    )
                except Exception as exc:
                    await websocket.send_json({"event": "error", "detail": str(exc)})
                continue

            if envelope.event == "call.accept":
                try:
                    payload = envelope.payload or {}
                    call_id = payload.get("call_id")
                    if not call_id:
                        await websocket.send_json(
                            {"event": "error", "detail": "call_id required"}
                        )
                        continue

                    if call_stub is None:
                        await websocket.send_json(
                            {"event": "error", "detail": "Call service unavailable"}
                        )
                        continue

                    metadata = (("authorization", f"Bearer {access_token}"),)
                    grpc_request = mess_pb2.AcceptCallRequest(call_id=call_id)
                    resp = await to_thread.run_sync(
                        lambda: call_stub.AcceptCall(grpc_request, metadata=metadata)
                    )

                    await websocket.send_json(
                        {
                            "event": "call.accepted",
                            "payload": {
                                "call_id": resp.call_id,
                                "token": getattr(resp, "token", None),
                                "ws_url": getattr(resp, "ws_url", None),
                            },
                        }
                    )
                except grpc.RpcError as exc:
                    await websocket.send_json(
                        {"event": "error", "detail": exc.details() or str(exc)}
                    )
                except Exception as exc:
                    await websocket.send_json({"event": "error", "detail": str(exc)})
                continue

            if envelope.event == "call.reject":
                try:
                    payload = envelope.payload or {}
                    call_id = payload.get("call_id")
                    if not call_id:
                        await websocket.send_json(
                            {"event": "error", "detail": "call_id required"}
                        )
                        continue

                    if call_stub is None:
                        await websocket.send_json(
                            {"event": "error", "detail": "Call service unavailable"}
                        )
                        continue

                    metadata = (("authorization", f"Bearer {access_token}"),)
                    grpc_request = mess_pb2.RejectCallRequest(call_id=call_id)
                    await to_thread.run_sync(
                        lambda: call_stub.RejectCall(grpc_request, metadata=metadata)
                    )

                    await websocket.send_json(
                        {"event": "call.rejected", "payload": {"call_id": call_id}}
                    )
                except grpc.RpcError as exc:
                    await websocket.send_json(
                        {"event": "error", "detail": exc.details() or str(exc)}
                    )
                except Exception as exc:
                    await websocket.send_json({"event": "error", "detail": str(exc)})
                continue

            if envelope.event == "call.end":
                try:
                    payload = envelope.payload or {}
                    call_id = payload.get("call_id")
                    if not call_id:
                        await websocket.send_json(
                            {"event": "error", "detail": "call_id required"}
                        )
                        continue

                    if call_stub is None:
                        await websocket.send_json(
                            {"event": "error", "detail": "Call service unavailable"}
                        )
                        continue

                    metadata = (("authorization", f"Bearer {access_token}"),)
                    grpc_request = mess_pb2.EndCallRequest(call_id=call_id)
                    await to_thread.run_sync(
                        lambda: call_stub.EndCall(grpc_request, metadata=metadata)
                    )

                    await websocket.send_json(
                        {"event": "call.ended", "payload": {"call_id": call_id}}
                    )
                except grpc.RpcError as exc:
                    await websocket.send_json(
                        {"event": "error", "detail": exc.details() or str(exc)}
                    )
                except Exception as exc:
                    await websocket.send_json({"event": "error", "detail": str(exc)})
                continue

            await websocket.send_json(
                {"event": "error", "detail": f"Unknown event: {envelope.event}"}
            )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for user=%s client=%s", str(current_user_id), client)
    except Exception as exc:
        logger.error(
            "Unexpected error in websocket loop user=%s error=%s",
            str(current_user_id),
            str(exc),
            exc_info=True,
        )
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
            with contextlib.suppress(Exception):
                await heartbeat_task

        with contextlib.suppress(Exception):
            await manager.disconnect(connection)

        with contextlib.suppress(Exception):
            await update_user_last_seen(current_user_id, force=True)

        with contextlib.suppress(Exception):
            await redis_client.remove_online_user(str(current_user_id))
            await redis_client.publish(
                settings.REDIS_EVENTS_CHANNEL,
                json.dumps(
                    {
                        "event": "user.online",
                        "payload": {
                            "user_id": str(current_user_id),
                            "is_online": False,
                        },
                    }
                ),
            )