import anyio
import strawberry

from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.utils.converter import from_grpc_user

from .types import AuthPayload, AuthTokens


@strawberry.type
class AuthMutations:
    @strawberry.mutation
    async def login(
        self,
        login: str,
        password: str,
        info: strawberry.Info[GraphQLContext],
    ) -> AuthPayload:
        """Аутентификация пользователя."""
        response = await anyio.to_thread.run_sync(
            lambda: info.context.auth_client.login(
                login,
                password,
                user_agent=info.context.request.headers.get("user-agent"),
                device_info=info.context.request.headers.get("x-device-info"),
            )
        )

        return AuthPayload(
            tokens=AuthTokens(
                access_token=response.access_token,
                refresh_token=response.refresh_token,
                expires_in=response.expires_in,
            ),
            user=from_grpc_user(response.user),
        )

    @strawberry.mutation
    async def logout_current(self, info: strawberry.Info[GraphQLContext]) -> bool:
        access_token = info.context.require_access_token()

        await anyio.to_thread.run_sync(
            lambda: info.context.auth_client.logout_current(access_token)
        )
        return True

    @strawberry.mutation
    async def revoke_session(
        self,
        session_id: str,
        info: strawberry.Info[GraphQLContext],
    ) -> bool:
        access_token = info.context.require_access_token()

        await anyio.to_thread.run_sync(
            lambda: info.context.auth_client.revoke_session(session_id, access_token)
        )
        return True

    @strawberry.mutation
    async def logout_all_other_sessions(
        self,
        info: strawberry.Info[GraphQLContext],
    ) -> bool:
        access_token = info.context.require_access_token()

        await anyio.to_thread.run_sync(
            lambda: info.context.auth_client.logout_all_other_sessions(access_token)
        )
        return True

    @strawberry.mutation
    async def refresh_token(
        self,
        refresh_token: str,
        info: strawberry.Info[GraphQLContext],
    ) -> AuthPayload:
        """Обновление access/refresh токенов."""
        response = await anyio.to_thread.run_sync(
            lambda: info.context.auth_client.refresh_token(refresh_token)
        )

        return AuthPayload(
            tokens=AuthTokens(
                access_token=response.access_token,
                refresh_token=response.refresh_token,
                expires_in=response.expires_in,
            ),
            user=from_grpc_user(response.user),
        )