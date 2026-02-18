from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime
from uuid import UUID
from typing import Optional, List
from .enums import (
    ChatType, MemberRole, MemberStatus, MessageType,
    ContactStatus, AccountStatus, PrivacyLevel
)

# ---------- User ----------
class UserBase(BaseModel):
    nick_name: str = Field(..., min_length=3, max_length=50)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    middle_name: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class UserUpdate(UserBase):
    password: Optional[str] = None

class UserResponse(UserBase):
    user_id: UUID
    is_online: bool
    last_seen: Optional[datetime]
    status: AccountStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Chat ----------
class ChatBase(BaseModel):
    chat_type: ChatType
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    is_public: bool = False
    max_members: int = 200

class ChatCreate(ChatBase):
    # При создании группы можно сразу передать список участников
    member_ids: Optional[List[UUID]] = None

class ChatUpdate(ChatBase):
    pass

class ChatResponse(ChatBase):
    chat_id: UUID
    creator_id: Optional[UUID]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- ChatMember ----------
class ChatMemberBase(BaseModel):
    role: MemberRole = MemberRole.member
    status: MemberStatus = MemberStatus.active

class ChatMemberCreate(ChatMemberBase):
    user_id: UUID

class ChatMemberResponse(ChatMemberBase):
    chat_id: UUID
    user_id: UUID
    joined_at: datetime
    left_at: Optional[datetime]
    banned_until: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ---------- Message ----------
class MessageBase(BaseModel):
    content: Optional[str] = None
    type: MessageType = MessageType.text
    message_metadata: Optional[dict] = None
    reply_to_id: Optional[int] = None

class MessageCreate(MessageBase):
    # ID чата обычно берётся из URL
    pass

class MessageUpdate(BaseModel):
    content: Optional[str] = None
    message_metadata: Optional[dict] = None

class MessageResponse(MessageBase):
    message_id: int
    chat_id: UUID
    sender_id: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime]
    is_edited: bool

    model_config = ConfigDict(from_attributes=True)


# ---------- Attachment ----------
class AttachmentBase(BaseModel):
    file_name: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None

class AttachmentResponse(AttachmentBase):
    attachment_id: UUID
    message_id: int
    storage_path: str
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Reaction ----------
class ReactionCreate(BaseModel):
    emoji: str = Field(..., min_length=1, max_length=10)

class ReactionResponse(ReactionCreate):
    message_id: int
    user_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Mention ----------
class MentionResponse(BaseModel):
    mention_id: int
    message_id: int
    mentioned_user_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Contact ----------
class ContactCreate(BaseModel):
    contact_user_id: UUID

class ContactUpdateStatus(BaseModel):
    status: ContactStatus

class ContactResponse(BaseModel):
    user_id: UUID
    contact_user_id: UUID
    status: ContactStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Privacy Settings ----------
class PrivacySettingsUpdate(BaseModel):
    who_can_write_me: Optional[PrivacyLevel] = None
    who_can_add_to_groups: Optional[PrivacyLevel] = None
    who_can_see_phone: Optional[PrivacyLevel] = None
    who_can_see_last_seen: Optional[PrivacyLevel] = None

class PrivacySettingsResponse(PrivacySettingsUpdate):
    user_id: UUID
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Session Event (для аудита, обычно только чтение) ----------
class SessionEventResponse(BaseModel):
    event_id: int
    user_id: UUID
    action: str
    device_info: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Audit Log (для администраторов) ----------
class AuditLogResponse(BaseModel):
    log_id: int
    user_id: Optional[UUID]
    action: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    details: Optional[dict]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Токены / Аутентификация ----------
class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class LoginRequest(BaseModel):
    login: str  # может быть email, phone или nick_name
    password: str
    device_info: Optional[dict] = None


class RegisterRequest(BaseModel):
    login: str
    password: str = Field(..., min_length=8)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    nick_name: Optional[str] = None


class Token(TokenPair):
    """Алиас для ответа с токенами."""
    pass


class RefreshRequest(RefreshTokenRequest):
    """Алиас для запроса обновления токена."""
    pass


class SessionInfo(BaseModel):
    device_info: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: Optional[datetime] = None


# ---------- Алиасы и доп. схемы для эндпоинтов ----------
MessageOut = MessageResponse
ChatOut = ChatResponse
ChatMemberOut = ChatMemberResponse
AuditLogOut = AuditLogResponse
ContactOut = ContactResponse


class ChatMemberUpdate(BaseModel):
    role: MemberRole


class MessageWithReactions(MessageResponse):
    reactions: List[dict] = []
    mentions: List[UUID] = []