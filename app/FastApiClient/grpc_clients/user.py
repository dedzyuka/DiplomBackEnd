import grpc
from FastApiClient.core.config import settings
# from FastApiClient.core.errors import GrpcError
from .base import BaseGrpcClient
from FastApiClient.protos.protobuf import mess_pb2, mess_pb2_grpc

class UserGrpcClient(BaseGrpcClient):
    def __init__(self):
        super().__init__(settings.USER_GRPC_SERVER)
        self.stub = mess_pb2_grpc.UserServiceStub(self.channel)

    def get_user(self, user_id: int) -> mess_pb2.User:
        request = mess_pb2.GetUserRequest(user_id=user_id)
        try:
            return self.stub.GetUser(request, timeout=5)
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def search_users(self, query: str, page: int = 1) -> mess_pb2.UsersListResponse:
        request = mess_pb2.SearchUsersRequest(query=query, page=page)
        try:
            return self.stub.SearchUsers(request, timeout=5)
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def get_my_profile(self) -> mess_pb2.User:
        # В реальности нужно передавать токен в метаданных, здесь опустим
        request = mess_pb2.Empty()
        try:
            return self.stub.GetMyProfile(request, timeout=5)
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def create_user(self, nick_name: str, email: str, password:str, phone: str) -> mess_pb2.User:
        request = mess_pb2.CreateUserRequest(nick_name=nick_name, email=email,password = password, phone = phone)
        try:
            return self.stub.CreateUser(request, timeout=5)
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def update_user(self, user_id: int, 
                    nick_name: str,
                    email: str,
                    first_name:str, 
                    last_name:str,
                    middle_name:str, 
                    phone:str, 
                    avatar_url:str,
                    bio:str ) -> mess_pb2.User:
        request = mess_pb2.UpdateUserRequest(user_id=user_id or "", 
                                             nick_name=nick_name or "", 
                                             email=email or "", 
                                             first_name = first_name or "", 
                                             last_name = last_name or "", 
                                             middle_name = middle_name or "",
                                             phone = phone or "",
                                             avatar_url = avatar_url or "",
                                             bio = bio or "")
        try:
            return self.stub.UpdateUser(request, timeout=5)
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def delete_user(self, user_id: int) -> None:
        request = mess_pb2.DeleteUserRequest(user_id=user_id)
        try:
            self.stub.DeleteUser(request, timeout=5)
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def update_privacy(self, setting: str) -> mess_pb2.PrivacySetting:
        request = mess_pb2.UpdatePrivacyRequest(setting=setting)
        try:
            return self.stub.UpdatePrivacy(request, timeout=5)
        except grpc.RpcError as e:
            self._handle_rpc_error(e)