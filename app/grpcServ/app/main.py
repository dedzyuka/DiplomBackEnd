
import asyncio
from grpc import aio

from services.user import UsersServicer
from protobuf import mess_pb2_grpc

async def serve():

    server = aio.server()
    mess_pb2_grpc.add_UserServiceServicer_to_server(UsersServicer(), server)
    server.add_insecure_port('[::]:50051')
    print("gRPC server running on port 50051")
    await server.start()
    await server.wait_for_termination()

if __name__ == '__main__':
    asyncio.run(serve())