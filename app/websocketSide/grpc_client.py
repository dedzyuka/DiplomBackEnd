import grpc

from protobuf import mess_pb2_grpc
from websocketSide.config import settings


def get_message_stub():
    channel = grpc.insecure_channel(settings.MESSAGE_GRPC_SERVER)
    return mess_pb2_grpc.MessageServiceStub(channel)