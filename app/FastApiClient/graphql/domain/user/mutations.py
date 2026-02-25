import strawberry
from typing import Optional

from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.utils.converter import from_grpc_user

from .types import PrivacySetting, User


@strawberry.type
class UserMutations:
    @strawberry.mutation
    async def create(
        self,
        nick_name: str,
        email: str,
        password: str,
        phone: str,
        info: strawberry.Info[GraphQLContext],
    ) -> User:
        grpc_user = info.context.user_client.create_user(nick_name, email, password, phone)
        return from_grpc_user(grpc_user)
    
    def _assert_owner(
        self,
        context: GraphQLContext,
        target_user_id: str,
        operation: str,
    ) -> None:
        """
        Strict auth policy for user profile mutations.

        - request must be authenticated
        - only owner can mutate own profile
        """
        if not context.current_user_id:
            raise PermissionError(f"Authorization required for {operation}")

        if context.current_user_id != target_user_id:
            raise PermissionError(f"You can {operation} only your own profile")


    @strawberry.mutation
    async def update(
        self,
        user_id: str,
        info: strawberry.Info[GraphQLContext],
        nick_name: Optional[str] = None,
        email: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        middle_name: Optional[str] = None,
        phone: Optional[str] = None,
        avatar_url: Optional[str] = None,
        bio: Optional[str] = None,
    ) -> Optional[User]:
        self._assert_owner(info.context, user_id, "update")
        print(info.context.current_user_id)
        

        grpc_user = info.context.user_client.update_user(
            user_id,
            nick_name or "",
            email or "",
            first_name or "",
            last_name or "",
            middle_name or "",
            phone or "",
            avatar_url or "",
            bio or "",
            access_token=info.context.access_token,
        )
        return from_grpc_user(grpc_user)

    @strawberry.mutation
    async def delete(self, id: str, info: strawberry.Info[GraphQLContext]) -> bool:
        self._assert_owner(info.context, id, "delete")
        

        info.context.user_client.delete_user(id, access_token=info.context.access_token)
        return True

    @strawberry.mutation
    async def update_privacy(self, setting: str, info: strawberry.Info[GraphQLContext]) -> PrivacySetting:
        if not info.context.current_user_id:
            raise PermissionError("Authorization required for update_privacy")

        response = info.context.user_client.update_privacy(
            info.context.current_user_id,
            setting,
            access_token=info.context.access_token,
        )

        reverse_map = {
            1: "everyone",
            2: "contacts",
            3: "nobody",
            0: "unspecified",
        }
        return PrivacySetting(setting=reverse_map.get(response.who_can_write_me, "unspecified"))
