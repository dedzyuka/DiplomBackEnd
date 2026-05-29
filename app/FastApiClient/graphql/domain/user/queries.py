import strawberry
from typing import List, Optional
from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.utils.converter import _ts_to_iso, from_grpc_user
from .types import User, PrivacySettings

@strawberry.type
class UserQueries:
    @strawberry.field
    async def get(self, id: str, info: strawberry.Info[GraphQLContext]) -> Optional[User]:
        grpc_user = info.context.user_client.get_user(id)
        if not grpc_user:
            return None
        is_online = await info.context.redis_client.sismember("ws:online_users", id)
        grpc_user.is_online = is_online
        return from_grpc_user(grpc_user)

    @strawberry.field
    async def search(
        self,
        query: str,
        page: int = 1,
        *,
        info: strawberry.Info[GraphQLContext],
    ) -> List[User]:
        response = info.context.user_client.search_users(query, page)
        users = []
        for u in response.users:
            is_online = await info.context.redis_client.sismember("ws:online_users", u.user_id)
            u.is_online = is_online
            users.append(from_grpc_user(u))
        return users

    @strawberry.field
    async def my_profile(self, info: strawberry.Info[GraphQLContext]) -> Optional[User]:
        grpc_user = info.context.user_client.get_my_profile(
            access_token=info.context.require_access_token()
        )
        if grpc_user:
            is_online = await info.context.redis_client.sismember("ws:online_users", grpc_user.user_id)
            grpc_user.is_online = is_online
        return from_grpc_user(grpc_user)


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