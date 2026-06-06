from datetime import timezone

from FastApiClient.graphql.domain.chat.types import Chat as GraphQLChat
from FastApiClient.graphql.domain.user.types import User as GraphQLUser
from FastApiClient.graphql.domain.message.types import (
    Message as GraphQLMessage,
    Attachment as GraphQLAttachment,
    Reaction as GraphQLReaction,
    MessageStatusInfo,
)
from FastApiClient.protos.protobuf import mess_pb2


def _ts_to_iso(ts) -> str:
    if ts is None:
        return ""

    try:
        dt = ts.ToDatetime()
    except Exception:
        return ""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.isoformat()


def from_grpc_user(grpc_user: mess_pb2.User) -> GraphQLUser:
    """Преобразует protobuf User в GraphQL User."""
    return GraphQLUser(
        user_id=grpc_user.user_id,
        nick_name=grpc_user.nick_name,
        first_name=grpc_user.first_name,
        last_name=grpc_user.last_name,
        middle_name=grpc_user.middle_name,
        email=grpc_user.email,
        phone=grpc_user.phone,
        avatar_url=grpc_user.avatar_url,
        bio=grpc_user.bio,
        last_seen=_ts_to_iso(grpc_user.last_seen),
        is_online=bool(grpc_user.is_online),
        status=str(grpc_user.status),
        email_verified=bool(grpc_user.email_verified),
        phone_verified=bool(grpc_user.phone_verified),
        is_admin=bool(grpc_user.is_admin),
        created_at=_ts_to_iso(grpc_user.created_at),
        updated_at=_ts_to_iso(grpc_user.updated_at),
    )


def from_grpc_chat(grpc_chat) -> GraphQLChat:
    dt = grpc_chat.created_at.ToDatetime().astimezone(timezone.utc)
    created_iso = dt.isoformat()

    # my_role: 0 = unspecified, 1 = owner, 2 = admin, 3 = member
    my_role = None
    if grpc_chat.my_role != 0:  # не unspecified
        role_map = {1: "owner", 2: "admin", 3: "member"}
        my_role = role_map.get(grpc_chat.my_role, "member")

    # join_policy: 0 = unspecified, 1 = invite_only, 2 = request_approval, 3 = open
    join_policy = None
    if grpc_chat.join_policy != 0:
        policy_map = {1: "invite_only", 2: "request_approval", 3: "open"}
        join_policy = policy_map.get(grpc_chat.join_policy, "invite_only")

    return GraphQLChat(
        chat_id=str(grpc_chat.chat_id),
        chat_type=str(grpc_chat.chat_type),
        name=getattr(grpc_chat, "name", None) if grpc_chat.HasField("name") else None,
        description=getattr(grpc_chat, "description", None) if grpc_chat.HasField("description") else None,
        avatar_url=getattr(grpc_chat, "avatar_url", None) if grpc_chat.HasField("avatar_url") else None,
        creator_id=getattr(grpc_chat, "creator_id", None) if grpc_chat.HasField("creator_id") else None,
        is_public=bool(grpc_chat.is_public),
        max_members=int(grpc_chat.max_members),
        created_at=created_iso,
        members_count=int(getattr(grpc_chat, "members_count", 0)),
        last_message=None,
        last_message_preview=None,
        my_role=my_role,
        join_policy=join_policy,
    )


# ----- Новые функции для конвертации attachment, reaction, status -----
def from_grpc_attachment(grpc_attachment) -> GraphQLAttachment:
    return GraphQLAttachment(
        attachment_id=grpc_attachment.attachment_id,
        file_name=grpc_attachment.file_name,
        file_size=grpc_attachment.file_size if grpc_attachment.HasField("file_size") else None,
        mime_type=grpc_attachment.mime_type if grpc_attachment.HasField("mime_type") else None,
        storage_path=grpc_attachment.storage_path,
        uploaded_at=_ts_to_iso(grpc_attachment.uploaded_at),
    )


def from_grpc_reaction(grpc_reaction) -> GraphQLReaction:
    return GraphQLReaction(
        message_id=grpc_reaction.message_id,
        user_id=grpc_reaction.user_id,
        emoji=grpc_reaction.emoji,
        created_at=_ts_to_iso(grpc_reaction.created_at),
    )


def from_grpc_message_status(grpc_status) -> MessageStatusInfo:
    return MessageStatusInfo(
        user_id=grpc_status.user_id,
        delivered_at=_ts_to_iso(grpc_status.delivered_at) if grpc_status.HasField("delivered_at") else None,
        read_at=_ts_to_iso(grpc_status.read_at) if grpc_status.HasField("read_at") else None,
    )


def from_grpc_message(grpc_msg: mess_pb2.Message, current_user_id: str) -> GraphQLMessage:
    attachments = [from_grpc_attachment(a) for a in grpc_msg.attachments]
    reactions = [from_grpc_reaction(r) for r in grpc_msg.reactions]
    
    delivered_at = None
    read_at = None
    for s in grpc_msg.statuses:
        if s.user_id == current_user_id:
            delivered_at = _ts_to_iso(s.delivered_at) if s.HasField("delivered_at") else None
            read_at = _ts_to_iso(s.read_at) if s.HasField("read_at") else None
            break

    return GraphQLMessage(
        message_id=grpc_msg.message_id,
        chat_id=grpc_msg.chat_id,
        sender_id=grpc_msg.sender_id,
        content=grpc_msg.content if grpc_msg.HasField("content") else None,
        type="text",
        reply_to_id=grpc_msg.reply_to_id if grpc_msg.HasField("reply_to_id") else None,
        is_edited=grpc_msg.is_edited,
        created_at=_ts_to_iso(grpc_msg.created_at),
        updated_at=_ts_to_iso(grpc_msg.updated_at),
        deleted_at=_ts_to_iso(grpc_msg.deleted_at) if grpc_msg.HasField("deleted_at") else None,
        attachments=attachments,
        reactions=reactions,
        statuses=[],
        delivered_at=delivered_at,
        read_at=read_at,
        forwarded_from_user_id=grpc_msg.forwarded_from_user_id if grpc_msg.HasField("forwarded_from_user_id") else None,
        forwarded_from_nickname=grpc_msg.forwarded_from_nickname if grpc_msg.HasField("forwarded_from_nickname") else None,
    )