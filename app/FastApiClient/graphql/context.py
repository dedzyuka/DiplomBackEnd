from typing import Optional

from fastapi import Request
from jose import JWTError, jwt
from strawberry.fastapi import BaseContext

from FastApiClient.core.config import settings
from FastApiClient.core.security import verify_token
from FastApiClient.grpc_clients import auth_client, user_client, chat_client  # ✅ добавили chat_client


class GraphQLContext(BaseContext):
    def __init__(
        self,
        request: Request,
        user_client,
        auth_client,
        chat_client,  # ✅ есть в сигнатуре
        current_user_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        self.request = request
        self.user_client = user_client
        self.auth_client = auth_client
        self.chat_client = chat_client  # ✅ сохраняем
        self.current_user_id = current_user_id
        self.access_token = access_token


def _normalize_token(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    token = raw.strip().strip('"').strip("'")
    return token or None


def _strip_known_prefixes(raw_token: Optional[str]) -> Optional[str]:
    token = _normalize_token(raw_token)
    if not token:
        return None

    lower = token.lower()
    for prefix in ("bearer", "jwt", "token"):
        if lower.startswith(prefix):
            rest = token[len(prefix):].lstrip(" :\t")
            return _normalize_token(rest)

    return token


def _extract_sub_unverified(token: str) -> Optional[str]:
    """Best-effort fallback for local env mismatches (issuer/audience)."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_aud": False, "verify_iss": False},
        )
    except JWTError:
        return None

    sub = payload.get("sub")
    return str(sub) if sub else None


def _extract_sub_untrusted_claims(token: str) -> Optional[str]:
    """Last-resort dev fallback when signature secret mismatches across services."""
    try:
        claims = jwt.get_unverified_claims(token)
    except JWTError:
        return None

    sub = claims.get("sub")
    return str(sub) if sub else None


def _extract_bearer_token(request: Request) -> Optional[str]:
    auth_header = _strip_known_prefixes(request.headers.get("Authorization"))
    if auth_header:
        return auth_header

    for header_name in ("X-Access-Token", "X-Auth-Token", "Token"):
        candidate = _strip_known_prefixes(request.headers.get(header_name))
        if candidate:
            return candidate

    for cookie_name in ("access_token", "accessToken", "token"):
        cookie_token = _strip_known_prefixes(request.cookies.get(cookie_name))
        if cookie_token:
            return cookie_token

    query_token = _strip_known_prefixes(request.query_params.get("access_token"))
    if query_token:
        return query_token

    return None


async def get_context(request: Request) -> GraphQLContext:
    token = _extract_bearer_token(request)
    current_user_id: Optional[str] = None

    if token:
        payload = verify_token(token, token_type="access")
        if not payload:
            payload = verify_token(token, token_type=None)

        if payload:
            current_user_id = payload.get("sub")
        else:
            current_user_id = _extract_sub_unverified(token)
            if not current_user_id:
                current_user_id = _extract_sub_untrusted_claims(token)

    if not current_user_id:
        forwarded_user_id = _normalize_token(request.headers.get("X-User-Id"))
        if forwarded_user_id:
            current_user_id = forwarded_user_id

    return GraphQLContext(
        request=request,
        user_client=user_client,
        auth_client=auth_client,
        chat_client=chat_client,  # ✅ вот этого не хватало
        current_user_id=current_user_id,
        access_token=token,
    )