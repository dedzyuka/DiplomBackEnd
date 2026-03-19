import anyio
import strawberry
from typing import List

from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.utils.converter import from_grpc_chat
from .types import Chat


@strawberry.type
class ChatQueries:
    @strawberry.field
    async def get(self, chat_id: str, info: strawberry.Info[GraphQLContext]) -> Chat:
        grpc_chat = await anyio.to_thread.run_sync(
            lambda: info.context.chat_client.get_chat(
                chat_id=chat_id,
                access_token=info.context.access_token,
                current_user_id=info.context.current_user_id,
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
        if not info.context.current_user_id:
            raise PermissionError("Authorization required")
        grpc_resp = await anyio.to_thread.run_sync(
            lambda: info.context.chat_client.list_chats(
                user_id=info.context.current_user_id,
                page=page,
                page_size=page_size,
                access_token=info.context.access_token,
                current_user_id=info.context.current_user_id,
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
    ) -> List[str]:
        grpc_resp = await anyio.to_thread.run_sync(
            lambda: info.context.chat_client.list_chat_members(
                chat_id=chat_id,
                page=page,
                page_size=page_size,
                access_token=info.context.access_token,
                current_user_id=info.context.current_user_id,
            )
        )
        return [member.user_id for member in grpc_resp.members]