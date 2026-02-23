import grpc
from FastApiClient.core.config import settings
from .base import BaseGrpcClient
from FastApiClient.protos.protobuf import mess_pb2, mess_pb2_grpc

class AuthGrpcClient(BaseGrpcClient):
    def __init__(self):
        super().__init__(settings.AUTH_GRPC_SERVER)
        self.stub = mess_pb2_grpc.AuthServiceStub(self.channel)

    def login(self, username: str, password: str) -> mess_pb2.LoginResponse:
        request = mess_pb2.LoginRequest(username=username, password=password)
        try:
            return self.stub.Login(request, timeout=5)
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def logout(self, token: str) -> None:
        request = mess_pb2_grpc.LogoutRequest(token=token)
        try:
            self.stub.Logout(request, timeout=5)
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def refresh_token(self, refresh_token: str) -> mess_pb2.LoginResponse:
        request = mess_pb2_grpc.RefreshTokenRequest(refresh_token=refresh_token)
        try:
            return self.stub.RefreshToken(request, timeout=5)
        except grpc.RpcError as e:
            self._handle_rpc_error(e)