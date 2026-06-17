from typing import Optional
import datetime
import enum
import uuid

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Enum, ForeignKeyConstraint, Index, Integer, LargeBinary, PrimaryKeyConstraint, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass


class AccountStatus(str, enum.Enum):
    ACTIVE = 'active'
    SUSPENDED = 'suspended'
    DELETED = 'deleted'


class ChatType(str, enum.Enum):
    PRIVATE = 'private'
    GROUP = 'group'
    CHANNEL = 'channel'


class ContactStatus(str, enum.Enum):
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'
    BLOCKED = 'blocked'


class MemberRole(str, enum.Enum):
    OWNER = 'owner'
    ADMIN = 'admin'
    MEMBER = 'member'


class MemberStatus(str, enum.Enum):
    ACTIVE = 'active'
    LEFT = 'left'
    BANNED = 'banned'


class MessageType(str, enum.Enum):
    TEXT = 'text'
    IMAGE = 'image'
    VIDEO = 'video'
    AUDIO = 'audio'
    FILE = 'file'
    LOCATION = 'location'
    CONTACT = 'contact'
    MIXED = 'mixed'


class PrivacyLevel(str, enum.Enum):
    EVERYONE = 'everyone'
    CONTACTS = 'contacts'
    NOBODY = 'nobody'


class Emoji(Base):
    __tablename__ = 'emoji'
    __table_args__ = (
        PrimaryKeyConstraint('emoji_id', name='emoji_pkey'),
        UniqueConstraint('code_point', name='emoji_code_point_key'),
        Index('idx_emoji_keywords', 'keywords', postgresql_using='gin'),
        Index('idx_emoji_name_trgm', 'name', postgresql_ops={'name': 'gin_trgm_ops'}, postgresql_using='gin')
    )

    emoji_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code_point: Mapped[str] = mapped_column(Text, nullable=False)
    character: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(Text)
    keywords: Mapped[Optional[dict]] = mapped_column(JSONB)


class Users(Base):
    __tablename__ = 'users'
    __table_args__ = (
        PrimaryKeyConstraint('user_id', name='users_pkey'),
        UniqueConstraint('email', name='users_email_key'),
        UniqueConstraint('nick_name', name='users_nick_name_key'),
        UniqueConstraint('phone', name='users_phone_key')
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    nick_name: Mapped[str] = mapped_column(String(50), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    salt: Mapped[str] = mapped_column(Text, nullable=False)
    is_online: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[AccountStatus] = mapped_column(Enum(AccountStatus, values_callable=lambda cls: [member.value for member in cls], name='account_status'), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    middle_name: Mapped[Optional[str]] = mapped_column(String(100))
    email: Mapped[Optional[str]] = mapped_column(String)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    bio: Mapped[Optional[str]] = mapped_column(Text)
    last_seen: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    audit_logs: Mapped[list['AuditLogs']] = relationship('AuditLogs', back_populates='user')
    chats: Mapped[list['Chats']] = relationship('Chats', back_populates='creator')
    contacts_contact_user: Mapped[list['Contacts']] = relationship('Contacts', foreign_keys='[Contacts.contact_user_id]', back_populates='contact_user')
    contacts_user: Mapped[list['Contacts']] = relationship('Contacts', foreign_keys='[Contacts.user_id]', back_populates='user')
    device_tokens: Mapped[list['DeviceTokens']] = relationship('DeviceTokens', back_populates='user')
    session_events: Mapped[list['SessionEvents']] = relationship('SessionEvents', back_populates='user')
    calls: Mapped[list['Calls']] = relationship('Calls', back_populates='initiator')
    chat_members: Mapped[list['ChatMembers']] = relationship('ChatMembers', back_populates='user')
    messages: Mapped[list['Messages']] = relationship('Messages', back_populates='sender')
    call_participants: Mapped[list['CallParticipants']] = relationship('CallParticipants', back_populates='user')
    mentions: Mapped[list['Mentions']] = relationship('Mentions', back_populates='mentioned_user')
    message_statuses: Mapped[list['MessageStatuses']] = relationship('MessageStatuses', back_populates='user')
    reactions: Mapped[list['Reactions']] = relationship('Reactions', back_populates='user')


class AuditLogs(Base):
    __tablename__ = 'audit_logs'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='SET NULL', name='audit_logs_user_id_fkey'),
        PrimaryKeyConstraint('log_id', 'created_at', name='audit_logs_pkey'),
        Index('idx_audit_details', 'details', postgresql_using='gin')
    )

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), primary_key=True, server_default=text('now()'))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    details: Mapped[Optional[dict]] = mapped_column(JSONB)

    user: Mapped[Optional['Users']] = relationship('Users', back_populates='audit_logs')


class Chats(Base):
    __tablename__ = 'chats'
    __table_args__ = (
        ForeignKeyConstraint(['creator_id'], ['users.user_id'], ondelete='SET NULL', name='chats_creator_id_fkey'),
        PrimaryKeyConstraint('chat_id', name='chats_pkey')
    )

    chat_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    chat_type: Mapped[ChatType] = mapped_column(Enum(ChatType, values_callable=lambda cls: [member.value for member in cls], name='chat_type'), nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False)
    max_members: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    name: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    creator_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('now()'))

    creator: Mapped[Optional['Users']] = relationship('Users', back_populates='chats')
    calls: Mapped[list['Calls']] = relationship('Calls', back_populates='chat')
    chat_members: Mapped[list['ChatMembers']] = relationship('ChatMembers', back_populates='chat')
    messages: Mapped[list['Messages']] = relationship('Messages', back_populates='chat')


class Contacts(Base):
    __tablename__ = 'contacts'
    __table_args__ = (
        CheckConstraint('user_id <> contact_user_id', name='no_self_contact'),
        ForeignKeyConstraint(['contact_user_id'], ['users.user_id'], ondelete='CASCADE', name='contacts_contact_user_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE', name='contacts_user_id_fkey'),
        PrimaryKeyConstraint('user_id', 'contact_user_id', name='contacts_pkey')
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    contact_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    status: Mapped[ContactStatus] = mapped_column(Enum(ContactStatus, values_callable=lambda cls: [member.value for member in cls], name='contact_status'), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    contact_user: Mapped['Users'] = relationship('Users', foreign_keys=[contact_user_id], back_populates='contacts_contact_user')
    user: Mapped['Users'] = relationship('Users', foreign_keys=[user_id], back_populates='contacts_user')


class DeviceTokens(Base):
    __tablename__ = 'device_tokens'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE', name='device_tokens_user_id_fkey'),
        PrimaryKeyConstraint('token_id', name='device_tokens_pkey'),
        UniqueConstraint('device_token', name='device_tokens_device_token_key'),
        Index('idx_device_tokens_user_id', 'user_id')
    )

    token_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    device_type: Mapped[str] = mapped_column(String(20), nullable=False)
    device_token: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    user: Mapped['Users'] = relationship('Users', back_populates='device_tokens')


class PrivacySettings(Users):
    __tablename__ = 'privacy_settings'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE', name='privacy_settings_user_id_fkey'),
        PrimaryKeyConstraint('user_id', name='privacy_settings_pkey')
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    who_can_write_me: Mapped[PrivacyLevel] = mapped_column(Enum(PrivacyLevel, values_callable=lambda cls: [member.value for member in cls], name='privacy_level'), nullable=False)
    who_can_add_to_groups: Mapped[PrivacyLevel] = mapped_column(Enum(PrivacyLevel, values_callable=lambda cls: [member.value for member in cls], name='privacy_level'), nullable=False)
    who_can_see_phone: Mapped[PrivacyLevel] = mapped_column(Enum(PrivacyLevel, values_callable=lambda cls: [member.value for member in cls], name='privacy_level'), nullable=False)
    who_can_see_last_seen: Mapped[PrivacyLevel] = mapped_column(Enum(PrivacyLevel, values_callable=lambda cls: [member.value for member in cls], name='privacy_level'), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))


class SessionEvents(Base):
    __tablename__ = 'session_events'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE', name='session_events_user_id_fkey'),
        PrimaryKeyConstraint('event_id', 'created_at', name='session_events_pkey')
    )

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), primary_key=True, server_default=text('now()'))
    refresh_token_hash: Mapped[Optional[str]] = mapped_column(Text)
    device_info: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped['Users'] = relationship('Users', back_populates='session_events')


class Calls(Base):
    __tablename__ = 'calls'
    __table_args__ = (
        ForeignKeyConstraint(['chat_id'], ['chats.chat_id'], ondelete='CASCADE', name='calls_chat_id_fkey'),
        ForeignKeyConstraint(['initiator_id'], ['users.user_id'], ondelete='CASCADE', name='calls_initiator_id_fkey'),
        PrimaryKeyConstraint('call_id', name='calls_pkey'),
        Index('idx_calls_chat_id', 'chat_id'),
        Index('idx_calls_status', 'status')
    )

    call_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    chat_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    initiator_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    ended_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    livekit_room_name: Mapped[Optional[str]] = mapped_column(Text)

    chat: Mapped['Chats'] = relationship('Chats', back_populates='calls')
    initiator: Mapped['Users'] = relationship('Users', back_populates='calls')
    call_participants: Mapped[list['CallParticipants']] = relationship('CallParticipants', back_populates='call')


class ChatMembers(Base):
    __tablename__ = 'chat_members'
    __table_args__ = (
        ForeignKeyConstraint(['chat_id'], ['chats.chat_id'], ondelete='CASCADE', name='chat_members_chat_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE', name='chat_members_user_id_fkey'),
        PrimaryKeyConstraint('chat_id', 'user_id', name='chat_members_pkey')
    )

    chat_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    role: Mapped[MemberRole] = mapped_column(Enum(MemberRole, values_callable=lambda cls: [member.value for member in cls], name='member_role'), nullable=False)
    status: Mapped[MemberStatus] = mapped_column(Enum(MemberStatus, values_callable=lambda cls: [member.value for member in cls], name='member_status'), nullable=False)
    joined_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    left_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    banned_until: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    chat: Mapped['Chats'] = relationship('Chats', back_populates='chat_members')
    user: Mapped['Users'] = relationship('Users', back_populates='chat_members')


class Messages(Base):
    __tablename__ = 'messages'
    __table_args__ = (
        ForeignKeyConstraint(['chat_id'], ['chats.chat_id'], ondelete='CASCADE', name='messages_chat_id_fkey'),
        ForeignKeyConstraint(['sender_id'], ['users.user_id'], ondelete='CASCADE', name='messages_sender_id_fkey'),
        PrimaryKeyConstraint('message_id', 'created_at', name='messages_pkey'),
        Index('idx_messages_chat_created', 'chat_id', 'created_at'),
        Index('idx_messages_metadata', 'message_metadata', postgresql_using='gin'),
        Index('idx_messages_sender', 'sender_id')
    )

    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    sender_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    type: Mapped[MessageType] = mapped_column(Enum(MessageType, values_callable=lambda cls: [member.value for member in cls], name='message_type'), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), primary_key=True, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    is_edited: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reply_to_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    content: Mapped[Optional[str]] = mapped_column(Text)
    encrypted_content: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    message_metadata: Mapped[Optional[dict]] = mapped_column(JSONB)
    deleted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    forwarded_from_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    forwarded_from_nickname: Mapped[Optional[str]] = mapped_column(String(100))

    chat: Mapped['Chats'] = relationship('Chats', back_populates='messages')
    sender: Mapped['Users'] = relationship('Users', back_populates='messages')
    attachments: Mapped[list['Attachments']] = relationship('Attachments', back_populates='messages')
    mentions: Mapped[list['Mentions']] = relationship('Mentions', back_populates='messages')
    message_statuses: Mapped[list['MessageStatuses']] = relationship('MessageStatuses', back_populates='messages')
    reactions: Mapped[list['Reactions']] = relationship('Reactions', back_populates='messages')


class Attachments(Base):
    __tablename__ = 'attachments'
    __table_args__ = (
        ForeignKeyConstraint(['message_id', 'message_created_at'], ['messages.message_id', 'messages.created_at'], ondelete='CASCADE', name='attachments_message_id_message_created_at_fkey'),
        PrimaryKeyConstraint('attachment_id', name='attachments_pkey')
    )

    attachment_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    is_circular: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    message_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    message_created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    duration: Mapped[Optional[int]] = mapped_column(Integer)
    waveform: Mapped[Optional[str]] = mapped_column(Text)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text)

    messages: Mapped[Optional['Messages']] = relationship('Messages', back_populates='attachments')


class CallParticipants(Base):
    __tablename__ = 'call_participants'
    __table_args__ = (
        ForeignKeyConstraint(['call_id'], ['calls.call_id'], ondelete='CASCADE', name='call_participants_call_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE', name='call_participants_user_id_fkey'),
        PrimaryKeyConstraint('call_id', 'user_id', name='call_participants_pkey')
    )

    call_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    joined_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    left_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    call: Mapped['Calls'] = relationship('Calls', back_populates='call_participants')
    user: Mapped['Users'] = relationship('Users', back_populates='call_participants')


class Mentions(Base):
    __tablename__ = 'mentions'
    __table_args__ = (
        ForeignKeyConstraint(['mentioned_user_id'], ['users.user_id'], ondelete='CASCADE', name='mentions_mentioned_user_id_fkey'),
        ForeignKeyConstraint(['message_id', 'message_created_at'], ['messages.message_id', 'messages.created_at'], ondelete='CASCADE', name='mentions_message_id_message_created_at_fkey'),
        PrimaryKeyConstraint('mention_id', name='mentions_pkey'),
        UniqueConstraint('message_id', 'mentioned_user_id', name='mentions_message_id_mentioned_user_id_key')
    )

    mention_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    mentioned_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    mentioned_user: Mapped['Users'] = relationship('Users', back_populates='mentions')
    messages: Mapped['Messages'] = relationship('Messages', back_populates='mentions')


class MessageStatuses(Base):
    __tablename__ = 'message_statuses'
    __table_args__ = (
        ForeignKeyConstraint(['message_id', 'message_created_at'], ['messages.message_id', 'messages.created_at'], ondelete='CASCADE', name='message_statuses_message_id_message_created_at_fkey'),
        ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE', name='message_statuses_user_id_fkey'),
        PrimaryKeyConstraint('message_id', 'user_id', name='message_statuses_pkey'),
        Index('idx_message_statuses_unread', 'user_id', 'message_id', postgresql_where='(read_at IS NULL)')
    )

    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    message_created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    delivered_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    read_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    messages: Mapped['Messages'] = relationship('Messages', back_populates='message_statuses')
    user: Mapped['Users'] = relationship('Users', back_populates='message_statuses')


class Reactions(Base):
    __tablename__ = 'reactions'
    __table_args__ = (
        ForeignKeyConstraint(['message_id', 'message_created_at'], ['messages.message_id', 'messages.created_at'], ondelete='CASCADE', name='reactions_message_id_message_created_at_fkey'),
        ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE', name='reactions_user_id_fkey'),
        PrimaryKeyConstraint('message_id', 'user_id', 'emoji', name='reactions_pkey')
    )

    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    message_created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    emoji: Mapped[str] = mapped_column(String(10), primary_key=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    messages: Mapped['Messages'] = relationship('Messages', back_populates='reactions')
    user: Mapped['Users'] = relationship('Users', back_populates='reactions')
