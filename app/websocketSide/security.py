from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from config import settingsA

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


ALGORITHM = settingsA.JWT_ALGORITHM


def _base_claims(expires_at: datetime, token_type: str) -> Dict:
    now = datetime.now(timezone.utc)
    return {
        "iss": settingsA.JWT_ISSUER,
        "aud": settingsA.JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(uuid4()),
        "type": token_type,
    }


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settingsA.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update(_base_claims(expire, token_type="access"))
    return jwt.encode(to_encode, settingsA.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settingsA.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update(_base_claims(expire, token_type="refresh"))
    return jwt.encode(to_encode, settingsA.SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str, token_type: Optional[str] = "access") -> Optional[Dict]:
    try:
        payload = jwt.decode(
            token,
            settingsA.SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=settingsA.JWT_AUDIENCE,
            issuer=settingsA.JWT_ISSUER,
        )
        if token_type and payload.get("type") != token_type:
            return None
        if not payload.get("sub"):
            return None
        return payload
    except JWTError:
        return None


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)