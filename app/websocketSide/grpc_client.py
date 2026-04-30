import grpc
from protobuf import mess_pb2, mess_pb2_grpc
from config import settings

def get_message_stub():
    channel = grpc.insecure_channel(settings.CHAT_GRPC_SERVER)  # MessageService на том же порту
    return mess_pb2_grpc.MessageServiceStub(channel)