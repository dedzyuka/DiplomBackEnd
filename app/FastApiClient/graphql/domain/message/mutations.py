import anyio
import strawberry
from typing import Optional, List

from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.graphql.domain.message.utils.converter import from_grpc_message
from FastApiClient.graphql.domain.message.types import Message, Reaction
from FastApiClient.utils.converter import from_grpc_reaction


@strawberry.type
class MessageMutations:
    @strawberry.mutation
    async def send_message(
        self,
        info: strawberry.Info[GraphQLContext],
        chat_id: str,
        content: str,
        reply_to_id: Optional[int] = None,
    ) -> Message:
        current_user_id = info.context.require_user_id()
        access_token = info.context.require_access_token()

        grpc_msg = await anyio.to_thread.run_sync(
            lambda: info.context.message_client.send_message(
                chat_id=chat_id,
                content=content,
                sender_id=current_user_id,
                reply_to_id=reply_to_id,
                access_token=access_token,
            )
        )
        return from_grpc_message(grpc_msg)

    @strawberry.mutation
    async def update_message(
        self,
        info: strawberry.Info[GraphQLContext],
        message_id: int,
        chat_id: str,
        content: str,
    ) -> Message:
        access_token = info.context.require_access_token()
        grpc_msg = await anyio.to_thread.run_sync(
            lambda: info.context.message_client.update_message(
                message_id=message_id,
                chat_id=chat_id,
                content=content,
                access_token=access_token,
            )
        )
        return from_grpc_message(grpc_msg)

    @strawberry.mutation
    async def delete_message(
        self,
        info: strawberry.Info[GraphQLContext],
        message_id: int,
        chat_id: str,
    ) -> bool:
        access_token = info.context.require_access_token()
        await anyio.to_thread.run_sync(
            lambda: info.context.message_client.delete_message(
                message_id=message_id,
                chat_id=chat_id,
                access_token=access_token,
            )
        )
        return True

    @strawberry.mutation
    async def add_reaction(
        self,
        info: strawberry.Info[GraphQLContext],
        message_id: int,
        chat_id: str,
        emoji: str,
    ) -> Reaction:
        access_token = info.context.require_access_token()
        grpc_reaction = await anyio.to_thread.run_sync(
            lambda: info.context.message_client.add_reaction(
                message_id=message_id,
                chat_id=chat_id,
                emoji=emoji,
                access_token=access_token,
            )
        )
        return from_grpc_reaction(grpc_reaction)

    @strawberry.mutation
    async def remove_reaction(
        self,
        info: strawberry.Info[GraphQLContext],
        message_id: int,
        chat_id: str,
        emoji: str,
    ) -> bool:
        access_token = info.context.require_access_token()
        await anyio.to_thread.run_sync(
            lambda: info.context.message_client.remove_reaction(
                message_id=message_id,
                chat_id=chat_id,
                emoji=emoji,
                access_token=access_token,
            )
        )
        return True

    @strawberry.mutation
    async def mark_as_delivered(
        self,
        info: strawberry.Info[GraphQLContext],
        message_id: int,
        chat_id: str,
    ) -> bool:
        access_token = info.context.require_access_token()
        await anyio.to_thread.run_sync(
            lambda: info.context.message_client.mark_as_delivered(
                message_id=message_id,
                chat_id=chat_id,
                access_token=access_token,
            )
        )
        return True

    @strawberry.mutation
    async def mark_as_read(
        self,
        info: strawberry.Info[GraphQLContext],
        message_id: int,
        chat_id: str,
    ) -> bool:
        access_token = info.context.require_access_token()
        await anyio.to_thread.run_sync(
            lambda: info.context.message_client.mark_as_read(
                message_id=message_id,
                chat_id=chat_id,
                access_token=access_token,
            )
        )
        return True