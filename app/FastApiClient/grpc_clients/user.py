import grpc

from FastApiClient.core.config import settings
from FastApiClient.protos.protobuf import mess_pb2, mess_pb2_grpc
from google.protobuf.empty_pb2 import Empty

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

    def search_users(
        self,
        query: str,
        page: int = 1,
        page_size: int = 20,
    ) -> mess_pb2.UsersListResponse:
        page = max(page, 1)
        page_size = max(page_size, 1)
        page_token = str((page - 1) * page_size)

        request = mess_pb2.SearchUsersRequest(
            query=query or "",
            page_size=page_size,
            page_token=page_token,
        )
        try:
            return self.stub.SearchUsers(request, timeout=5)
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def get_my_profile(self, access_token: str | None = None) -> mess_pb2.User:
        request = Empty()
        try:
            return self.stub.GetMyProfile(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def create_user(
        self,
        nick_name: str,
        email: str,
        password: str,
        phone: str,
    ) -> mess_pb2.User:
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

    def update_privacy(
        self,
        *,
        user_id: str,
        who_can_write_me: str | None = None,
        who_can_add_to_groups: str | None = None,
        who_can_see_phone: str | None = None,
        who_can_see_last_seen: str | None = None,
        access_token: str | None = None,
    ):
        privacy_map = {
            None: 0,
            "everyone": 1,
            "contacts": 2,
            "nobody": 3,
        }

        request = mess_pb2.UpdatePrivacyRequest(
            user_id=str(user_id),
            who_can_write_me=privacy_map.get(who_can_write_me, 0),
            who_can_add_to_groups=privacy_map.get(who_can_add_to_groups, 0),
            who_can_see_phone=privacy_map.get(who_can_see_phone, 0),
            who_can_see_last_seen=privacy_map.get(who_can_see_last_seen, 0),
        )

        try:
            return self.stub.UpdatePrivacy(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def get_my_privacy(self, access_token: str | None = None) -> mess_pb2.PrivacySetting:
        request = Empty()
        try:
            return self.stub.GetMyPrivacy(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)