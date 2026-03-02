
import strawberry


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