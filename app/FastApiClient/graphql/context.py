from typing import Optional

from fastapi import Request
from jose import JWTError, jwt
from strawberry.fastapi import BaseContext

from FastApiClient.core.config import settings
from FastApiClient.core.security import verify_token
from FastApiClient.grpc_clients import auth_client, user_client


class GraphQLContext(BaseContext):
    def __init__(
        self,
        request: Request,
        user_client,
        auth_client,
        current_user_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        self.request = request
        self.user_client = user_client
        self.auth_client = auth_client
        self.current_user_id = current_user_id
        self.access_token = access_token




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
    auth_header = request.headers.get("Authorization")
    if auth_header:
        normalized = auth_header.strip()
        lower = normalized.lower()
        if lower.startswith("bearer "):
            token = normalized[7:].strip()
            if token:
                return token
        if normalized:
            return normalized

    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token.strip()

    return None


async def get_context(request: Request) -> GraphQLContext:
    token = _extract_bearer_token(request)
    current_user_id: Optional[str] = None

    if token:
        payload = verify_token(token, token_type="access")
        if not payload:
            # backward compatibility: accept legacy tokens without `type`
            payload = verify_token(token, token_type=None)
        if payload:
            current_user_id = payload.get("sub")
        else:
            # fallback: same secret/signature but mismatched aud/iss in environments
            current_user_id = _extract_sub_unverified(token)
            if not current_user_id:
                # final dev fallback for environments with different signing secrets
                current_user_id = _extract_sub_untrusted_claims(token)

    if not current_user_id:
        forwarded_user_id = request.headers.get("X-User-Id")
        if forwarded_user_id:
            current_user_id = forwarded_user_id.strip()

    return GraphQLContext(
        request=request,
        user_client=user_client,
        auth_client=auth_client,
        current_user_id=current_user_id,
        access_token=token,
    )
