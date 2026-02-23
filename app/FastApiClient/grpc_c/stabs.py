import grpc
from FastApiClient.protos.protobuf.mess_pb2_grpc import UserServiceStub, AuthServiceStub


channel = grpc.insecure_channel("todo_grpc:50051")
UserStub = UserServiceStub(channel)
AuthStab = AuthServiceStub(channel)