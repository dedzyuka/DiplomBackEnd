import strawberry
from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.utils.converter import from_grpc_user
from .types import LoginResponse

@strawberry.type
class AuthMutations:
    @strawberry.mutation
    async def login(self, username: str, password: str, info: strawberry.Info[GraphQLContext]) -> LoginResponse:
        """Аутентификация пользователя."""
        response = info.context.auth_client.login(username, password)
        return LoginResponse(
            token=response.token,
            user=from_grpc_user(response.user)
        )

    @strawberry.mutation
    async def logout(self, token: str, info: strawberry.Info[GraphQLContext]) -> bool:
        """Выход из системы."""
        info.context.auth_client.logout(token)
        return True

    @strawberry.mutation
    async def refresh_token(self, refresh_token: str, info: strawberry.Info[GraphQLContext]) -> LoginResponse:
        """Обновление access token."""
        response = info.context.auth_client.refresh_token(refresh_token)
        return LoginResponse(
            token=response.token,
            user=from_grpc_user(response.user)
        )