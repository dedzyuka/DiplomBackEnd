from typing import Optional

from fastapi import Request
from strawberry.fastapi import BaseContext

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


def _extract_bearer_token(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    try:
        schema, token = auth_header.split(" ", 1)
    except ValueError:
        return None
    if schema.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def get_context(request: Request) -> GraphQLContext:
    token = _extract_bearer_token(request)
    current_user_id: Optional[str] = None

    if token:
        payload = verify_token(token, token_type="access")
        if payload:
            current_user_id = payload.get("sub")

    return GraphQLContext(
        request=request,
        user_client=user_client,
        auth_client=auth_client,
        current_user_id=current_user_id,
        access_token=token,
    )
