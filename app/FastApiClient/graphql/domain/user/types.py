from typing import Optional

import strawberry


@strawberry.type
class User:
    user_id: str
    nick_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    last_seen: Optional[str] = None
    is_online: bool = False
    status: str = "active"
    email_verified: bool = False
    phone_verified: bool = False
    is_admin: bool = False
    created_at: str = ""
    updated_at: str = ""

    @strawberry.field
    def id(self) -> str:
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

@strawberry.type
class PrivacySettings:
    who_can_write_me: str
    who_can_add_to_groups: str
    who_can_see_phone: str
    who_can_see_last_seen: str
    updated_at: Optional[str] = None