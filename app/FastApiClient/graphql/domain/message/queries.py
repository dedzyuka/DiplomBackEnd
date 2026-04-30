import anyio
import strawberry
from typing import List

from FastApiClient.graphql.context import GraphQLContext
from .utils.converter import from_grpc_message
from .types import Message

@strawberry.type
class MessageQueries:
    @strawberry.field
    async def get_message(
        self,
        info: strawberry.Info[GraphQLContext],
        message_id: int,
        chat_id: str,
    ) -> Message:
        access_token = info.context.require_access_token()
        grpc_msg = await anyio.to_thread.run_sync(
            lambda: info.context.message_client.get_message(
                message_id=message_id,
                chat_id=chat_id,
                access_token=access_token,
            )
        )
        return from_grpc_message(grpc_msg)

    @strawberry.field
    async def list_messages(
        self,
        info: strawberry.Info[GraphQLContext],
        chat_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> List[Message]:
        access_token = info.context.require_access_token()
        resp = await anyio.to_thread.run_sync(
            lambda: info.context.message_client.list_messages(
                chat_id=chat_id,
                page=page,
                page_size=page_size,
                access_token=access_token,
            )
        )
        return [from_grpc_message(msg) for msg in resp.messages]