import strawberry

from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.utils.converter import from_grpc_user

from .types import AuthPayload, AuthTokens


@strawberry.type
class AuthMutations:
    @strawberry.mutation
    async def login(self, login: str, password: str, info: strawberry.Info[GraphQLContext]) -> AuthPayload:
        """Аутентификация пользователя."""
        response = info.context.auth_client.login(login, password)
        return AuthPayload(
            tokens=AuthTokens(
                access_token=response.access_token,
                refresh_token=response.refresh_token,
                expires_in=response.expires_in,
            ),
            user=from_grpc_user(response.user),
        )

    @strawberry.mutation
    async def logout(self, refresh_token: str, info: strawberry.Info[GraphQLContext]) -> bool:
        """Выход из системы (ревокация refresh-сессии)."""
        info.context.auth_client.logout(refresh_token)
        return True

    @strawberry.mutation
    async def refresh_token(self, refresh_token: str, info: strawberry.Info[GraphQLContext]) -> AuthPayload:
        """Обновление access/refresh токенов."""
        response = info.context.auth_client.refresh_token(refresh_token)
        return AuthPayload(
            tokens=AuthTokens(
                access_token=response.access_token,
                refresh_token=response.refresh_token,
                expires_in=response.expires_in,
            ),
            user=from_grpc_user(response.user),
        )