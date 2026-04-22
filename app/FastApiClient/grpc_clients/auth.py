import grpc
from typing import Optional

from FastApiClient.core.config import settings
from FastApiClient.protos.protobuf import mess_pb2, mess_pb2_grpc

from .base import BaseGrpcClient


class AuthGrpcClient(BaseGrpcClient):
    def __init__(self):
        super().__init__(settings.AUTH_GRPC_SERVER)
        self.stub = mess_pb2_grpc.AuthServiceStub(self.channel)

    @staticmethod
    def _auth_metadata(
        access_token: Optional[str] = None,
        user_agent: Optional[str] = None,
        device_info: Optional[str] = None,
    ):
        metadata = []

        if access_token:
            metadata.append(("authorization", f"Bearer {access_token}"))

        if user_agent:
            metadata.append(("x-user-agent", user_agent))

        if device_info:
            metadata.append(("x-device-info", device_info))

        return tuple(metadata) if metadata else None

    def login(
        self,
        login: str,
        password: str,
        *,
        user_agent: Optional[str] = None,
        device_info: Optional[str] = None,
    ) -> mess_pb2.LoginResponse:
        request = mess_pb2.LoginRequest(login=login, password=password)
        try:
            return self.stub.Login(
                request,
                timeout=5,
                metadata=self._auth_metadata(
                    user_agent=user_agent,
                    device_info=device_info,
                ),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def refresh_token(self, refresh_token: str) -> mess_pb2.LoginResponse:
        request = mess_pb2.RefreshTokenRequest(refresh_token=refresh_token)
        try:
            return self.stub.RefreshToken(request, timeout=5)
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def list_sessions(self, access_token: str):
        try:
            return self.stub.ListSessions(
                mess_pb2.ListSessionsRequest(),
                timeout=5,
                metadata=self._auth_metadata(access_token=access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def logout_current(self, access_token: str) -> None:
        try:
            self.stub.LogoutCurrentSession(
                mess_pb2.LogoutCurrentSessionRequest(),
                timeout=5,
                metadata=self._auth_metadata(access_token=access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def revoke_session(self, session_id: str, access_token: str) -> None:
        try:
            self.stub.RevokeSession(
                mess_pb2.RevokeSessionRequest(session_id=session_id),
                timeout=5,
                metadata=self._auth_metadata(access_token=access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def logout_all_other_sessions(self, access_token: str) -> None:
        try:
            self.stub.LogoutAllOtherSessions(
                mess_pb2.LogoutAllOtherSessionsRequest(),
                timeout=5,
                metadata=self._auth_metadata(access_token=access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)