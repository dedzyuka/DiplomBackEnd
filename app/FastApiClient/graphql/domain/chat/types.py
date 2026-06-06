

from typing import Optional, List
import strawberry
from FastApiClient.graphql.domain.user.types import User

# Существующий тип MessagePreview
@strawberry.type
class MessagePreview:
    message_id: int
    sender_id: str
    sender_nickname: str | None = None
    text_preview: str | None
    created_at: str
    type: str

@strawberry.type
class Chat:
    chat_id: str
    chat_type: str
    name: str | None
    description: str | None
    avatar_url: str | None
    creator_id: str | None
    is_public: bool
    max_members: int
    created_at: str
    last_message: str | None = None
    members_count: int = 0
    last_message_preview: Optional[MessagePreview] = None
    my_role: Optional[str] = None          # <-- новое поле
    join_policy: Optional[str] = None      # <-- новое поле

@strawberry.type
class ChatMember:
    user: User
    role: str
    status: str
    joined_at: str
    left_at: Optional[str] = None
    banned_until: Optional[str] = None