import strawberry
from typing import Optional

from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.utils.converter import from_grpc_user
from FastApiClient.graphql.domain.user.types import PrivacySettings, PrivacyUpdateInput, User


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
    ) -> tuple[str, str]:
        current_user_id = context.require_user_id()
        access_token = context.require_access_token()

        if current_user_id != target_user_id:
            raise PermissionError(f"You can {operation} only your own profile")

        return current_user_id, access_token

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
        _, access_token = self._assert_owner(info.context, user_id, "update")

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
            access_token=access_token,
        )
        return from_grpc_user(grpc_user)

    @strawberry.mutation
    async def delete(self, id: str, info: strawberry.Info[GraphQLContext]) -> bool:
        _, access_token = self._assert_owner(info.context, id, "delete")

        info.context.user_client.delete_user(id, access_token=access_token)
        return True

    @strawberry.mutation
    async def update_privacy(
        self,
        input: PrivacyUpdateInput,
        info: strawberry.Info[GraphQLContext],
    ) -> PrivacySettings:
        current_user_id = info.context.require_user_id()
        access_token = info.context.require_access_token()

        allowed = {"everyone", "contacts", "nobody"}

        def normalize(value: str | None, field_name: str) -> str | None:
            if value is None:
                return None
            normalized = value.strip().lower()
            if normalized not in allowed:
                raise ValueError(
                    f"{field_name} must be one of: everyone, contacts, nobody"
                )
            return normalized

        who_can_write_me = normalize(input.who_can_write_me, "who_can_write_me")
        who_can_add_to_groups = normalize(input.who_can_add_to_groups, "who_can_add_to_groups")
        who_can_see_phone = normalize(input.who_can_see_phone, "who_can_see_phone")
        who_can_see_last_seen = normalize(input.who_can_see_last_seen, "who_can_see_last_seen")

        if all(
            value is None
            for value in (
                who_can_write_me,
                who_can_add_to_groups,
                who_can_see_phone,
                who_can_see_last_seen,
            )
        ):
            raise ValueError("At least one privacy field must be provided")

        response = info.context.user_client.update_privacy(
            user_id=current_user_id,
            who_can_write_me=who_can_write_me,
            who_can_add_to_groups=who_can_add_to_groups,
            who_can_see_phone=who_can_see_phone,
            who_can_see_last_seen=who_can_see_last_seen,
            access_token=access_token,
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
        )