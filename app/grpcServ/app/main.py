import asyncio
from grpc import aio

from services.message import MessageServicer
from services.chat import ChatServicer
from services.contact import ContactServicer
from protobuf import mess_pb2_grpc

from services.redis_client import redis_client
from services.auth import AuthServicer
from services.user import UsersServicer
from services.attachment import AttachmentServicer
from services.call import CallServicer


async def serve():
    await redis_client.ping()

    server = aio.server()
    mess_pb2_grpc.add_UserServiceServicer_to_server(UsersServicer(), server)
    mess_pb2_grpc.add_AuthServiceServicer_to_server(AuthServicer(), server)
    mess_pb2_grpc.add_ChatServiceServicer_to_server(ChatServicer(), server)
    mess_pb2_grpc.add_MessageServiceServicer_to_server(MessageServicer(), server)
    mess_pb2_grpc.add_ContactServiceServicer_to_server(ContactServicer(), server)
    mess_pb2_grpc.add_AttachmentServiceServicer_to_server(AttachmentServicer(), server)
    mess_pb2_grpc.add_CallServiceServicer_to_server(CallServicer(), server)

    server.add_insecure_port("[::]:50051")
    server.add_insecure_port("[::]:50052")
    server.add_insecure_port("[::]:50053")
    server.add_insecure_port("[::]:50054")
    server.add_insecure_port("[::]:50055")
    server.add_insecure_port("[::]:50056")
    server.add_insecure_port("[::]:50057")

    print("gRPC server running on ports 50051 (UserService) and 50052 (AuthService)")
    print("gRPC server running on ports 50053 (ChatServise) and 50054 (MessageService)")
    print("gRPC server running on ports 50055 (ContactServise) and 50057 (CallService)")
    await server.start()
    try:
        await server.wait_for_termination()
    finally:
        await redis_client.close()


if __name__ == "__main__":
    asyncio.run(serve())