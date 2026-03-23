from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import redis.asyncio as redis
from jose import JWTError, jwt

from FastApiClient.core.config import settings


@dataclass(slots=True)
class AccessSessionPrincipal:
    user_id: str
    session_id: str
    payload: dict
    access_token: str


_redis_client: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    return _redis_client


def _session_key(session_id: str) -> str:
    return f"{settings.REDIS_PREFIX}:auth:session:{session_id}"


async def verify_access_session(token: str) -> Optional[AccessSessionPrincipal]:
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

    if payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    session_id = payload.get("sid")

    if not user_id or not session_id:
        return None

    session_data = await _get_redis().hgetall(_session_key(str(session_id)))
    if not session_data:
        return None

    # сессия должна принадлежать тому же пользователю
    if session_data.get("user_id") != str(user_id):
        return None

    # пока auth service хранит access_token в Redis — используем это как жёсткую проверку
    stored_access_token = session_data.get("access_token")
    if stored_access_token and stored_access_token != token:
        return None

    return AccessSessionPrincipal(
        user_id=str(user_id),
        session_id=str(session_id),
        payload=payload,
        access_token=token,
    )