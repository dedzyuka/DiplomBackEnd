import anyio
import strawberry
from typing import List

from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.utils.converter import from_grpc_chat, from_grpc_user
from FastApiClient.graphql.domain.user.types import User
from .types import Chat


@strawberry.type
class ChatQueries:
    @strawberry.field
    async def get(self, chat_id: str, info: strawberry.Info[GraphQLContext]) -> Chat:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()

        grpc_chat = await anyio.to_thread.run_sync(
            lambda: info.context.chat_client.get_chat(
                chat_id=chat_id,
                access_token=access_token,
                current_user_id=current_user_id,
            )
        )
        return from_grpc_chat(grpc_chat)

    @strawberry.field
    async def list(
        self,
        info: strawberry.Info[GraphQLContext],
        page: int = 1,
        page_size: int = 20,
    ) -> List[Chat]:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()

        grpc_resp = await anyio.to_thread.run_sync(
            lambda: info.context.chat_client.list_chats(
                user_id=current_user_id,
                page=page,
                page_size=page_size,
                access_token=access_token,
                current_user_id=current_user_id,
            )
        )
        return [from_grpc_chat(chat) for chat in grpc_resp.chats]

    @strawberry.field
    async def members(
        self,
        chat_id: str,
        info: strawberry.Info[GraphQLContext],
        page: int = 1,
        page_size: int = 50,
    ) -> List[User]:   # изменён тип возврата
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()

        grpc_resp = await anyio.to_thread.run_sync(
            lambda: info.context.chat_client.list_chat_members(
                chat_id=chat_id,
                page=page,
                page_size=page_size,
                access_token=access_token,
                current_user_id=current_user_id,
            )
        )
        # grpc_resp.members – список объектов ChatMember, у каждого есть user_id
        users = []
        for member in grpc_resp.members:
            # Получаем пользователя через user_client
            grpc_user = await anyio.to_thread.run_sync(
                lambda: info.context.user_client.get_user(member.user_id)
            )
            if grpc_user:
                is_online = await info.context.redis_client.sismember("ws:online_users", grpc_user.user_id)
                grpc_user.is_online = is_online
                users.append(from_grpc_user(grpc_user))
        return users
