import strawberry
from typing import Optional, List

@strawberry.type
class MessageStatusInfo:
    user_id: str
    delivered_at: Optional[str] = None
    read_at: Optional[str] = None

@strawberry.type
class Message:
    message_id: int
    chat_id: str
    sender_id: str
    content: Optional[str] = None
    type: str = "text"
    reply_to_id: Optional[int] = None
    is_edited: bool = False
    created_at: str
    updated_at: str
    deleted_at: Optional[str] = None
    statuses: Optional[MessageStatusInfo] = strawberry.field(default_factory=list)