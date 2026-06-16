# websocketSide/sessionauth.py

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from typing import Optional

import redis.asyncio as redis
from jose import JWTError, jwt

from websocketSide.config import settings

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_PREFIX = os.getenv("REDIS_PREFIX", "messenger")

redis_client: Optional[redis.Redis] = None


@dataclass(slots=True)
class AccessSessionPrincipal:
    userid: str
    sessionid: str
    payload: dict
    accesstoken: str


@dataclass(slots=True)
class AccessSessionCheckResult:
    ok: bool
    principal: Optional[AccessSessionPrincipal] = None
    reason: str = "unknown"


def get_redis() -> redis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client


def session_key(session_id: str) -> str:
    return f"{REDIS_PREFIX}:auth:session:{session_id}"


def mask_token(token: str | None, head: int = 16, tail: int = 8) -> str:
    if not token:
        return "<empty>"
    if len(token) <= head + tail:
        return token
    return f"{token[:head]}...{token[-tail:]}"


async def verify_access_session_detailed(token: str) -> AccessSessionCheckResult:
    if not token:
        return AccessSessionCheckResult(ok=False, reason="token_missing")

    try:
        payload = jwt.decode(
            token,
            settings.SECRETKEY,
            algorithms=[settings.JWTALGORITHM],
            audience=settings.JWTAUDIENCE,
            issuer=settings.JWTISSUER,
        )
    except JWTError as e:
        logger.warning("WS auth failed: jwt_invalid error=%s", str(e))
        return AccessSessionCheckResult(ok=False, reason="jwt_invalid")

    if payload.get("type") != "access":
        logger.warning("WS auth failed: wrong_token_type type=%s", payload.get("type"))
        return AccessSessionCheckResult(ok=False, reason="wrong_token_type")

    userid = payload.get("sub")
    sessionid = payload.get("sid")

    if not userid or not sessionid:
        logger.warning(
            "WS auth failed: missing_claims sub=%s sid=%s",
            userid,
            sessionid,
        )
        return AccessSessionCheckResult(ok=False, reason="missing_claims")

    key = session_key(str(sessionid))
    sessiondata = await get_redis().hgetall(key)

    if not sessiondata:
        logger.warning(
            "WS auth failed: session_not_found redis_key=%s sub=%s sid=%s",
            key,
            userid,
            sessionid,
        )
        return AccessSessionCheckResult(ok=False, reason="session_not_found")

    stored_userid = sessiondata.get("userid")
    if stored_userid != str(userid):
        logger.warning(
            "WS auth failed: session_user_mismatch token_sub=%s redis_userid=%s sid=%s",
            userid,
            stored_userid,
            sessionid,
        )
        return AccessSessionCheckResult(ok=False, reason="session_user_mismatch")

    stored_access_token = sessiondata.get("accesstoken")
    if stored_access_token and stored_access_token != token:
        logger.warning(
            "WS auth failed: access_token_mismatch sid=%s token=%s redis_token=%s",
            sessionid,
            mask_token(token),
            mask_token(stored_access_token),
        )
        return AccessSessionCheckResult(ok=False, reason="access_token_mismatch")

    return AccessSessionCheckResult(
        ok=True,
        principal=AccessSessionPrincipal(
            userid=str(userid),
            sessionid=str(sessionid),
            payload=payload,
            accesstoken=token,
        ),
        reason="ok",
    )


async def verifyaccesssession(token: str) -> Optional[AccessSessionPrincipal]:
    result = await verify_access_session_detailed(token)
    return result.principal if result.ok else None