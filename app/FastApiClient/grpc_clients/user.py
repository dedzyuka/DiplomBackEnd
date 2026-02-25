import grpc

from FastApiClient.core.config import settings
from FastApiClient.protos.protobuf import mess_pb2, mess_pb2_grpc

from .base import BaseGrpcClient


class UserGrpcClient(BaseGrpcClient):
    def __init__(self):
        super().__init__(settings.USER_GRPC_SERVER)
        self.stub = mess_pb2_grpc.UserServiceStub(self.channel)

    @staticmethod
    def _auth_metadata(access_token: str | None):
        if access_token:
            return (("authorization", f"Bearer {access_token}"),)
        return None

    def get_user(self, user_id: str) -> mess_pb2.User:
        request = mess_pb2.GetUserRequest(user_id=str(user_id))
        try:
            return self.stub.GetUser(request, timeout=5)
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def search_users(self, query: str, page: int = 1, page_size: int = 20) -> mess_pb2.UsersListResponse:
        page = max(page, 1)
        page_token = str((page - 1) * page_size)
        request = mess_pb2.SearchUsersRequest(query=query, page_size=page_size, page_token=page_token)
        try:
            return self.stub.SearchUsers(request, timeout=5)
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def get_my_profile(self, access_token: str | None = None) -> mess_pb2.User:
        request = mess_pb2.Empty()
        try:
            return self.stub.GetMyProfile(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def create_user(self, nick_name: str, email: str, password: str, phone: str) -> mess_pb2.User:
        request = mess_pb2.CreateUserRequest(
            nick_name=nick_name,
            email=email,
            password=password,
            phone=phone,
        )
        try:
            return self.stub.CreateUser(request, timeout=5)
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def update_user(
        self,
        user_id: str,
        nick_name: str,
        email: str,
        first_name: str,
        last_name: str,
        middle_name: str,
        phone: str,
        avatar_url: str,
        bio: str,
        access_token: str | None = None,
    ) -> mess_pb2.User:
        request = mess_pb2.UpdateUserRequest(
            user_id=str(user_id),
            nick_name=nick_name or "",
            email=email or "",
            first_name=first_name or "",
            last_name=last_name or "",
            middle_name=middle_name or "",
            phone=phone or "",
            avatar_url=avatar_url or "",
            bio=bio or "",
        )
        try:
            return self.stub.UpdateUser(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def delete_user(self, user_id: str, access_token: str | None = None) -> None:
        request = mess_pb2.DeleteUserRequest(user_id=str(user_id))
        try:
            self.stub.DeleteUser(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def update_privacy(self, user_id: str, setting: str, access_token: str | None = None) -> mess_pb2.PrivacySetting:
        level_map = {
            "everyone": mess_pb2.PrivacyLevel.EVERYONE,
            "contacts": mess_pb2.PrivacyLevel.CONTACTS,
            "nobody": mess_pb2.PrivacyLevel.NOBODY,
        }
        level = level_map.get(setting.lower(), mess_pb2.PrivacyLevel.PRIVACY_LEVEL_UNSPECIFIED)
        request = mess_pb2.UpdatePrivacyRequest(user_id=str(user_id), who_can_write_me=level)
        try:
            return self.stub.UpdatePrivacy(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)
