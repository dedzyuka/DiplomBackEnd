from typing import Optional
import strawberry


@strawberry.type
class User:
    user_id: str
    nick_name: str
    first_name: str
    last_name: str
    middle_name: str
    email: str
    phone: str
    avatar_url: str
    bio: str
    last_seen: str
    is_online: str
    status: str
    email_verified: str
    phone_verified: str
    is_admin: str
    created_at: str
    updated_at: str

    @strawberry.field
    def id(self) -> str:
        """Backward-compatible GraphQL alias for `user_id`."""
        return self.user_id


@strawberry.type
class PrivacySettings:
    who_can_write_me: str
    who_can_add_to_groups: str
    who_can_see_phone: str
    who_can_see_last_seen: str

@strawberry.input
class PrivacyUpdateInput:
    who_can_write_me: Optional[str] = None
    who_can_add_to_groups: Optional[str] = None
    who_can_see_phone: Optional[str] = None
    who_can_see_last_seen: Optional[str] = None