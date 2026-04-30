from FastApiClient.protos.protobuf import mess_pb2
from FastApiClient.graphql.domain.message.types import Message as GQLMessage, MessageStatusInfo
from FastApiClient.utils.converter import _ts_to_iso

def from_grpc_message(grpc_msg: mess_pb2.Message) -> GQLMessage:
    return GQLMessage(
        message_id=grpc_msg.message_id,
        chat_id=grpc_msg.chat_id,
        sender_id=grpc_msg.sender_id,
        content=grpc_msg.content if grpc_msg.HasField("content") else None,
        type="text",  # можно маппинг
        reply_to_id=grpc_msg.reply_to_id if grpc_msg.HasField("reply_to_id") else None,
        is_edited=grpc_msg.is_edited,
        created_at=_ts_to_iso(grpc_msg.created_at),
        updated_at=_ts_to_iso(grpc_msg.updated_at),
        deleted_at=_ts_to_iso(grpc_msg.deleted_at) if grpc_msg.HasField("deleted_at") else None,
        statuses=[
            MessageStatusInfo(
                user_id=s.user_id,
                delivered_at=_ts_to_iso(s.delivered_at) if s.HasField("delivered_at") else None,
                read_at=_ts_to_iso(s.read_at) if s.HasField("read_at") else None,
            ) for s in grpc_msg.statuses
        ],
    )