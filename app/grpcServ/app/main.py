import asyncio
from grpc import aio

from protobuf import mess_pb2_grpc

from services.redis_client import redis_client
from services.auth import AuthServicer
from services.user import UsersServicer


async def serve():
    await redis_client.ping()

    server = aio.server()
    mess_pb2_grpc.add_UserServiceServicer_to_server(UsersServicer(), server)
    mess_pb2_grpc.add_AuthServiceServicer_to_server(AuthServicer(), server)

    server.add_insecure_port("[::]:50051")
    server.add_insecure_port("[::]:50052")

    print("gRPC server running on ports 50051 (UserService) and 50052 (AuthService)")
    await server.start()
    try:
        await server.wait_for_termination()
    finally:
        await redis_client.close()


if __name__ == "__main__":
    asyncio.run(serve())