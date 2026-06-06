import anyio
import strawberry
from typing import List

from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.graphql.domain.message.utils.converter import from_grpc_message
from FastApiClient.graphql.domain.message.types import Message


@strawberry.type
class MessageQueries:
    @strawberry.field
    async def list_messages(
        self,
        info: strawberry.Info[GraphQLContext],
        chat_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> List[Message]:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        resp = await anyio.to_thread.run_sync(
            lambda: info.context.message_client.list_messages(
                chat_id=chat_id,
                page=page,
                page_size=page_size,
                access_token=access_token,
            )
        )
        return [from_grpc_message(msg, current_user_id) for msg in resp.messages]

    @strawberry.field
    async def get_message(
        self,
        info: strawberry.Info[GraphQLContext],
        message_id: int,
        chat_id: str,
    ) -> Message:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        grpc_msg = await anyio.to_thread.run_sync(
            lambda: info.context.message_client.get_message(
                message_id=message_id,
                chat_id=chat_id,
                access_token=access_token,
            )
        )
        return from_grpc_message(grpc_msg, current_user_id)

    @strawberry.field
    async def search_messages(
        self,
        info: strawberry.Info[GraphQLContext],
        chat_id: str,
        query: str,
        page: int = 1,
        page_size: int = 50,
    ) -> List[Message]:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()          # ДОБАВЛЕНО
        resp = await anyio.to_thread.run_sync(
            lambda: info.context.message_client.search_messages(
                chat_id=chat_id,
                query=query,
                page=page,
                page_size=page_size,
                access_token=access_token,
            )
        )
        return [from_grpc_message(msg, current_user_id) for msg in resp.messages] 