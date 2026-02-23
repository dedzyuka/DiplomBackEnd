# types/user_types.py
import strawberry
from FastApiClient.grpc_c.stabs import UserServiceStub
from FastApiClient.protos.protobuf import mess_pb2

@strawberry.type
class User:
    user_id: int
    name: str
    email: str

# @strawberry.type
# class UserQueries:
#     @strawberry.field
#     async def get(self, user_id: int) -> User:
#         req = mess_pb2.UserService.GetUserRequest(user_id=user_id)
#         resp = user_client.GetUser(req)
#         return User.from_grpc(resp)

#     @strawberry.field
#     async def search(self, query: str, page: int = 1) -> list[User]:
#         req = mess_pb2.SearchUsersRequest(query=query, page=page)
#         resp = user_client.SearchUsers(req)
#         return [User.from_grpc(u) for u in resp.users]

#     @strawberry.field
#     async def my_profile(self) -> User:
#         req = google_dot_protobuf_empty_pb2.Empty()
#         resp = user_client.GetMyProfile(req)
#         return User.from_grpc(resp)

@strawberry.type
class UserMutations:
    @strawberry.mutation
    async def create(self, name: str, email: str) -> User:
        req = mess_pb2.CreateUserRequest(name=name, email=email)
        resp = UserServiceStub.CreateUser(req)
        return User.from_grpc(resp)

    # @strawberry.mutation
    # async def update(self, user_id: int, name: str, email: str) -> User:
    #     req = users_pb2.UpdateUserRequest(user_id=user_id, name=name, email=email)
    #     resp = user_client.UpdateUser(req)
    #     return User.from_grpc(resp)

    # @strawberry.mutation
    # async def delete(self, user_id: int) -> bool:
    #     req = users_pb2.DeleteUserRequest(user_id=user_id)
    #     user_client.DeleteUser(req)
    #     return True

    # @strawberry.mutation
    # async def update_privacy(self, setting: str) -> PrivacySetting:
    #     req = users_pb2.UpdatePrivacyRequest(setting=setting)
    #     resp = user_client.UpdatePrivacy(req)
    #     return PrivacySetting.from_grpc(resp)