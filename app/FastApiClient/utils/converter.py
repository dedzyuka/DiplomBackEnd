from datetime import timezone

from FastApiClient.graphql.domain.chat.types import Chat as GraphQLChat
from FastApiClient.graphql.domain.user.types import User as GraphQLUser
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
    )