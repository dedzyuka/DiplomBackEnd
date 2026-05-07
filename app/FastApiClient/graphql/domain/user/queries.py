from typing import List, Optional

import strawberry

from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.utils.converter import _ts_to_iso, from_grpc_user
from .types import User
from .types import PrivacySettings


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
        grpc_user = info.context.user_client.get_my_profile(
            access_token=info.context.require_access_token()
        )
        return from_grpc_user(grpc_user)
    

    @strawberry.field
    async def my_privacy(self, info: strawberry.Info[GraphQLContext]) -> PrivacySettings:
        response = info.context.user_client.get_my_privacy(
            access_token=info.context.require_access_token()
        )

        reverse_map = {
            1: "everyone",
            2: "contacts",
            3: "nobody",
            0: "unspecified",
        }

        return PrivacySettings(
            who_can_write_me=reverse_map.get(response.who_can_write_me, "unspecified"),
            who_can_add_to_groups=reverse_map.get(response.who_can_add_to_groups, "unspecified"),
            who_can_see_phone=reverse_map.get(response.who_can_see_phone, "unspecified"),
            who_can_see_last_seen=reverse_map.get(response.who_can_see_last_seen, "unspecified"),
            updated_at=_ts_to_iso(response.updated_at),
        )