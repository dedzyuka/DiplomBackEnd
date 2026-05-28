from typing import ClassVar, Optional
from sqlalchemy import (
    Column, ForeignKeyConstraint, PrimaryKeyConstraint, String, Text, Boolean, ForeignKey, UniqueConstraint,
    CheckConstraint, Index, JSON, BigInteger, Integer, LargeBinary,
    TIMESTAMP, Enum as SQLEnum, UUID, text
)

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
import uuid

from FastApiClient.database import Base

from .enums import (
    ChatType, MemberRole, MemberStatus, MessageType,
    ContactStatus, AccountStatus, PrivacyLevel
)

# Для генерации UUID по умолчанию используем функцию gen_random_uuid() из pgcrypto
# но можно оставить генерацию на уровне Python: default=uuid.uuid4
def generate_uuid():
    return str(uuid.uuid4())

# ---------- Users ----------
class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    nick_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String, unique=True)  # citext в БД, но здесь String
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    salt: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    bio: Mapped[str | None] = mapped_column(Text)
    last_seen: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[AccountStatus] = mapped_column(
        SQLEnum(AccountStatus, name="account_status"), default=AccountStatus.active
    )
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    # Relationships
    owned_chats = relationship("Chat", back_populates="creator")
    chat_memberships = relationship("ChatMember", back_populates="user")
    sent_messages = relationship("Message", back_populates="sender")
    message_statuses = relationship("MessageStatus", back_populates="user")
    reactions = relationship("Reaction", back_populates="user")
    mentions = relationship("Mention", back_populates="mentioned_user")
    contacts_from = relationship(
        "Contact", foreign_keys="Contact.user_id", back_populates="user"
    )
    contacts_to = relationship(
        "Contact", foreign_keys="Contact.contact_user_id", back_populates="contact_user"
    )
    privacy = relationship("PrivacySetting", back_populates="user", uselist=False)
    session_events = relationship("SessionEvent", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")


# ---------- Chats ----------
class Chat(Base):
    __tablename__ = "chats"

    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    chat_type: Mapped[ChatType] = mapped_column(SQLEnum(ChatType, name="chat_type"))
    name: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    creator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL")
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    max_members: Mapped[int] = mapped_column(Integer, default=200)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    # Relationships
    creator = relationship("User", back_populates="owned_chats")
    members = relationship("ChatMember", back_populates="chat")
    messages = relationship("Message", back_populates="chat")


# ---------- Chat Members ----------
class ChatMember(Base):
    __tablename__ = "chat_members"

    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chats.chat_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[MemberRole] = mapped_column(
        SQLEnum(MemberRole, name="member_role"), default=MemberRole.member
    )
    status: Mapped[MemberStatus] = mapped_column(
        SQLEnum(MemberStatus, name="member_status"), default=MemberStatus.active
    )
    joined_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    left_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    banned_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # Relationships
    chat = relationship("Chat", back_populates="members")
    user = relationship("User", back_populates="chat_memberships")


# ---------- Messages (partitioned) ----------
class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # Составной первичный ключ включает created_at для партиционирования
        PrimaryKeyConstraint("message_id", "created_at"),
        # Индексы
        Index("idx_messages_chat_created", "chat_id", "created_at"),
        Index("idx_messages_sender", "sender_id"),
        Index("idx_messages_metadata", "message_metadata", postgresql_using="gin"),
    )

    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chats.chat_id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    reply_to_id: Mapped[int | None] = mapped_column(BigInteger)  # без внешнего ключа
    content: Mapped[str | None] = mapped_column(Text)
    encrypted_content: Mapped[bytes | None] = mapped_column(LargeBinary)
    type: Mapped[MessageType] = mapped_column(
        SQLEnum(MessageType, name="message_type"), default=MessageType.text
    )
    message_metadata: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), primary_key=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    chat = relationship("Chat", back_populates="messages")
    sender = relationship("User", back_populates="sent_messages")
    statuses = relationship("MessageStatus", back_populates="message")
    attachments = relationship("Attachment", back_populates="message")
    reactions = relationship("Reaction", back_populates="message")
    mentions = relationship("Mention", back_populates="message")


# ---------- Message Statuses (partitioned by hash) ----------
class MessageStatus(Base):
    __tablename__ = "message_statuses"
    __table_args__ = (
        # Внешний ключ к messages составной
        ForeignKeyConstraint(
            ["message_id", "message_created_at"],
            ["messages.message_id", "messages.created_at"],
            ondelete="CASCADE"
        ),
        PrimaryKeyConstraint("message_id", "user_id"),
        Index("idx_message_statuses_unread", "user_id", "message_id",
              postgresql_where=text("read_at IS NULL")),
    )

    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    message_created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # Relationships
    message = relationship("Message", back_populates="statuses")
    user = relationship("User", back_populates="message_statuses")


# ---------- Attachments ----------
class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["message_id", "message_created_at"],
            ["messages.message_id", "messages.created_at"],
            ondelete="CASCADE"
        ),
    )

    attachment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    # Relationships
    message = relationship("Message", back_populates="attachments")


# ---------- Reactions ----------
class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["message_id", "message_created_at"],
            ["messages.message_id", "messages.created_at"],
            ondelete="CASCADE"
        ),
        PrimaryKeyConstraint("message_id", "user_id", "emoji"),
    )

    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    message_created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    emoji: Mapped[str] = mapped_column(String(10), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    # Relationships
    message = relationship("Message", back_populates="reactions")
    user = relationship("User", back_populates="reactions")


# ---------- Mentions ----------
class Mention(Base):
    __tablename__ = "mentions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["message_id", "message_created_at"],
            ["messages.message_id", "messages.created_at"],
            ondelete="CASCADE"
        ),
        UniqueConstraint("message_id", "mentioned_user_id"),
    )

    mention_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    mentioned_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    # Relationships
    message = relationship("Message", back_populates="mentions")
    mentioned_user = relationship("User", back_populates="mentions")


# ---------- Contacts ----------
class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "contact_user_id"),
        CheckConstraint("user_id <> contact_user_id", name="no_self_contact"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    contact_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[ContactStatus] = mapped_column(
        SQLEnum(ContactStatus, name="contact_status"), default=ContactStatus.pending
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="contacts_from")
    contact_user = relationship("User", foreign_keys=[contact_user_id], back_populates="contacts_to")


# ---------- Privacy Settings ----------
class PrivacySetting(Base):
    __tablename__ = "privacy_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    who_can_write_me: Mapped[PrivacyLevel] = mapped_column(
        SQLEnum(PrivacyLevel, name="privacy_level"), default=PrivacyLevel.everyone
    )
    who_can_add_to_groups: Mapped[PrivacyLevel] = mapped_column(
        SQLEnum(PrivacyLevel, name="privacy_level"), default=PrivacyLevel.everyone
    )
    who_can_see_phone: Mapped[PrivacyLevel] = mapped_column(
        SQLEnum(PrivacyLevel, name="privacy_level"), default=PrivacyLevel.contacts
    )
    who_can_see_last_seen: Mapped[PrivacyLevel] = mapped_column(
        SQLEnum(PrivacyLevel, name="privacy_level"), default=PrivacyLevel.everyone
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    # Relationships
    user = relationship("User", back_populates="privacy")


# ---------- Session Events (audit) ----------
class SessionEvent(Base):
    __tablename__ = "session_events"
    __table_args__ = (
        PrimaryKeyConstraint("event_id", "created_at"),
    )

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # login, logout, revoke, refresh
    refresh_token_hash: Mapped[str | None] = mapped_column(Text)
    device_info: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))  # inet в БД, но как строка
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), primary_key=True
    )

    # Relationships
    user = relationship("User", back_populates="session_events")


# ---------- Audit Logs ----------
class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        PrimaryKeyConstraint("log_id", "created_at"),
        Index("idx_audit_details", "details", postgresql_using="gin"),
    )

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), primary_key=True
    )

    # Relationships
    user = relationship("User", back_populates="audit_logs")


# ---------- Emoji Dictionary ----------
class Emoji(Base):
    __tablename__ = "emoji"
    __table_args__ = (
        Index("idx_emoji_keywords", "keywords", postgresql_using="gin"),
        Index("idx_emoji_name_trgm", "name", postgresql_using="gin"),
    )

    emoji_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code_point: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    character: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str] | None] = mapped_column(JSONB)  # массив строк