from FastApiClient.protos.protobuf import mess_pb2
from FastApiClient.graphql.domain.user.types import User as GraphQLUser

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