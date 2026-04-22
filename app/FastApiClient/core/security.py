# app/FastApiClient/core/security.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Literal, Optional
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from FastApiClient.core.config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = settings.JWT_ALGORITHM
TokenType = Literal["access", "refresh"]


def _base_claims(expires_at: datetime, token_type: TokenType) -> Dict:
    now = datetime.now(timezone.utc)
    return {
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(uuid4()),
        "type": token_type,
    }


def _build_session_token(
    *,
    user_id: str,
    session_id: str,
    token_type: TokenType,
    expires_delta: timedelta,
) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": user_id,
        "sid": session_id,
        **_base_claims(expire, token_type=token_type),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(
    user_id: str,
    session_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    return _build_session_token(
        user_id=user_id,
        session_id=session_id,
        token_type="access",
        expires_delta=expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(
    user_id: str,
    session_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    return _build_session_token(
        user_id=user_id,
        session_id=session_id,
        token_type="refresh",
        expires_delta=expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def verify_token(token: str, token_type: Optional[TokenType] = "access") -> Optional[Dict]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
    except JWTError:
        return None

    if token_type and payload.get("type") != token_type:
        return None

    if not payload.get("sub") or not payload.get("sid"):
        return None

    return payload


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)