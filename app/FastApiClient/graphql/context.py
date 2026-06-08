from typing import Optional
from fastapi import Request
from strawberry.fastapi import BaseContext
from FastApiClient.core.session_auth import verify_access_session
from FastApiClient.grpc_clients import auth_client, user_client, chat_client, message_client, contact_client
from FastApiClient.core.redis_client import redis_client as global_redis_client
from FastApiClient.grpc_clients import call_client


class GraphQLContext(BaseContext):
    def __init__(
        self,
        request: Request,
        user_client,
        auth_client,
        chat_client,
        contact_client,
        current_user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        access_token: Optional[str] = None,
        is_access_token_verified: bool = False,
        redis_client=None,
        call_client = None
    ):
        self.request = request
        self.user_client = user_client
        self.auth_client = auth_client
        self.chat_client = chat_client
        self.contact_client = contact_client
        self.message_client = message_client
        self.current_user_id = current_user_id
        self.session_id = session_id
        self.access_token = access_token
        self.is_access_token_verified = is_access_token_verified
        self.redis_client = redis_client or global_redis_client
        self.call_client = call_client


    def require_access_token(self) -> str:
        if not self.is_access_token_verified or not self.access_token:
            raise PermissionError("Missing or invalid access token")
        return self.access_token

    def require_user_id(self) -> str:
        if not self.is_access_token_verified or not self.current_user_id:
            raise PermissionError("Authorization required")
        return self.current_user_id

    def require_session_id(self) -> str:
        if not self.is_access_token_verified or not self.session_id:
            raise PermissionError("Authorization required")
        return self.session_id


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

    return None


async def get_context(request: Request) -> GraphQLContext:
    token = _extract_bearer_token(request)
    current_user_id: Optional[str] = None
    session_id: Optional[str] = None
    is_access_token_verified = False
    verified_access_token: Optional[str] = None

    if token:
        principal = await verify_access_session(token)
        if principal:
            current_user_id = principal.user_id
            session_id = principal.session_id
            is_access_token_verified = True
            verified_access_token = principal.access_token

    return GraphQLContext(
        request=request,
        user_client=user_client,
        auth_client=auth_client,
        chat_client=chat_client,
        contact_client=contact_client,
        current_user_id=current_user_id,
        session_id=session_id,
        access_token=verified_access_token,
        is_access_token_verified=is_access_token_verified,
        redis_client=global_redis_client,   # передаём
        call_client=call_client,
    )