from typing import List, Optional

import strawberry

from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.utils.converter import from_grpc_user
from .types import User


@strawberry.type
class UserQueries:
    @strawberry.field
    async def get(self, id: str, info: strawberry.Info[GraphQLContext]) -> Optional[User]:
        """Получить пользователя по ID."""
        try:
            grpc_user = info.context.user_client.get_user(id)
            return from_grpc_user(grpc_user)
        except ValueError:
            return None

    @strawberry.field
    async def search(
        self,
        query: str,
        page: int = 1,
        *,
        info: strawberry.Info[GraphQLContext],
    ) -> List[User]:
        """Поиск пользователей."""
        response = info.context.user_client.search_users(query, page)
        return [from_grpc_user(u) for u in response.users]

    @strawberry.field
    async def my_profile(self, info: strawberry.Info[GraphQLContext]) -> Optional[User]:
        """Получить профиль текущего пользователя."""
        if not info.context.access_token:
            raise PermissionError("Authorization required")

        grpc_user = info.context.user_client.get_my_profile(
            access_token=info.context.access_token
        )
        return from_grpc_user(grpc_user)