from strawberry.fastapi import BaseContext  # правильный импорт
from typing import Optional
from fastapi import Request
from FastApiClient.grpc_clients import user_client, auth_client

class GraphQLContext(BaseContext):  # наследуемся от BaseContext, без декоратора
    def __init__(self, request: Request, user_client, auth_client, current_user_id: Optional[int] = None):
        self.request = request
        self.user_client = user_client
        self.auth_client = auth_client
        self.current_user_id = current_user_id

async def get_context(request: Request) -> GraphQLContext:
    # Здесь можно извлечь токен из заголовка Authorization и установить current_user_id
    return GraphQLContext(
        request=request,
        user_client=user_client,
        auth_client=auth_client,
        current_user_id=None
    )