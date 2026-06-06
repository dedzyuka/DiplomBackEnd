import strawberry
from typing import Optional, List

@strawberry.type
class Attachment:
    attachment_id: str
    file_name: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    storage_path: str
    uploaded_at: str

@strawberry.type
class Reaction:
    message_id: int
    user_id: str
    emoji: str
    created_at: str

@strawberry.type
class MessageStatusInfo:
    user_id: str
    delivered_at: Optional[str] = None
    read_at: Optional[str] = None

@strawberry.type
class MessagePreview:
    message_id: int
    sender_id: str
    sender_nickname: Optional[str] = None
    text_preview: Optional[str] = None
    created_at: str
    type: str

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
    attachments: List[Attachment] = strawberry.field(default_factory=list)
    reactions: List[Reaction] = strawberry.field(default_factory=list)
    statuses: List[MessageStatusInfo] = strawberry.field(default_factory=list)
    delivered_at: Optional[str] = None
    read_at: Optional[str] = None
    forwarded_from_user_id: Optional[str] = None       # ДОБАВЛЕНО
    forwarded_from_nickname: Optional[str] = None      # ДОБАВЛЕНО