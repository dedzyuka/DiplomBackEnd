from __future__ import annotations

from dataclasses import dataclass
import uuid

import grpc
from jose import JWTError, jwt

from core.config import settings
from services.redis_client import redis_client


@dataclass(slots=True)
class AccessSessionPrincipal:
    user_id: str
    session_id: str
    access_token: str
    payload: dict


def _extract_bearer_token(context) -> str | None:
    metadata = context.invocation_metadata() if context else None
    auth_header = None

    if metadata:
        for item in metadata:
            key = (item.key or "").lower()
            if key == "authorization":
                auth_header = item.value
                break

    if not auth_header:
        return None

    token = auth_header.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    return token or None


async def resolve_access_session(context) -> AccessSessionPrincipal | None:
    token = _extract_bearer_token(context)
    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
    except JWTError:
        return None
    except Exception:
        return None

    if payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    session_id = payload.get("sid")
    if not user_id or not session_id:
        return None

    session_data = await redis_client.get_session_tokens(str(session_id))
    if not session_data:
        return None

    if session_data.get("user_id") != str(user_id):
        return None

    stored_access_token = session_data.get("access_token")
    if stored_access_token and stored_access_token != token:
        return None

    return AccessSessionPrincipal(
        user_id=str(user_id),
        session_id=str(session_id),
        access_token=token,
        payload=payload,
    )


async def require_current_user_id(context) -> str:
    principal = await resolve_access_session(context)
    if not principal:
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid or revoked access session")
    return principal.user_id


async def require_current_user_uuid(context) -> uuid.UUID:
    user_id = await require_current_user_id(context)
    try:
        return uuid.UUID(str(user_id))
    except Exception:
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid current_user_id in token")