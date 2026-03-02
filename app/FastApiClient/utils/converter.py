from datetime import timezone
from FastApiClient.protos.protobuf import mess_pb2
from FastApiClient.graphql.domain.user.types import User as GraphQLUser
from FastApiClient.models import Chat

def from_grpc_user(grpc_user: mess_pb2.User) -> GraphQLUser:
    """Преобразует protobuf User в GraphQL User."""
    return GraphQLUser(
        user_id=grpc_user.user_id,
        nick_name=grpc_user.nick_name,          # было name -> исправлено
        first_name=grpc_user.first_name,
        last_name=grpc_user.last_name,
        middle_name=grpc_user.middle_name,
        email=grpc_user.email,
        phone=grpc_user.phone,
        avatar_url=grpc_user.avatar_url,
        bio=grpc_user.bio,
        last_seen=str(grpc_user.last_seen.seconds),  # преобразуем в строку
        is_online=grpc_user.is_online,
        status=str(grpc_user.status),                 # если статус enum, возможно нужно .name или .value
        email_verified=grpc_user.email_verified,
        phone_verified=grpc_user.phone_verified,
        is_admin=grpc_user.is_admin,
        created_at=str(grpc_user.created_at.seconds),
        updated_at=str(grpc_user.updated_at.seconds),
    )
def from_grpc_chat(grpc_chat) -> Chat:
    # grpc_chat.created_at: google.protobuf.Timestamp
    # В python protobuf у Timestamp есть .ToDatetime()
    dt = grpc_chat.created_at.ToDatetime().astimezone(timezone.utc)
    created_iso = dt.isoformat()

    return Chat(
        chat_id=str(grpc_chat.chat_id),
        chat_type=str(grpc_chat.chat_type),  # можно маппить в "private/group/channel" при желании

        name=getattr(grpc_chat, "name", None) if grpc_chat.HasField("name") else None,
        description=getattr(grpc_chat, "description", None) if grpc_chat.HasField("description") else None,
        avatar_url=getattr(grpc_chat, "avatar_url", None) if grpc_chat.HasField("avatar_url") else None,
        creator_id=getattr(grpc_chat, "creator_id", None) if grpc_chat.HasField("creator_id") else None,

        is_public=bool(grpc_chat.is_public),
        max_members=int(grpc_chat.max_members),
        created_at=created_iso,

        members_count=int(grpc_chat.members_count),
    )