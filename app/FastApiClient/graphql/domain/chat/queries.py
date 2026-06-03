import anyio
import strawberry
from typing import List

from FastApiClient.graphql.context import GraphQLContext
from .types import MessagePreview as GQLMessagePreview
from FastApiClient.utils.converter import from_grpc_chat, _ts_to_iso, from_grpc_user
from FastApiClient.graphql.domain.user.types import User
from .types import Chat


def _to_message_preview(grpc_preview):
    """Конвертирует protobuf MessagePreview в GraphQL MessagePreview (один аргумент)."""
    if not grpc_preview:
        return None

    return GQLMessagePreview(
        message_id=grpc_preview.message_id,
        sender_id=grpc_preview.sender_id,
        sender_nickname=None,  # можно позже подгрузить через дополнительный запрос
        text_preview=grpc_preview.text_preview if grpc_preview.HasField("text_preview") else None,
        created_at=_ts_to_iso(grpc_preview.created_at),
        type=str(grpc_preview.type),
    )


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
        gql_chat = from_grpc_chat(grpc_chat)
        if grpc_chat.HasField("last_message_preview"):
            gql_chat.last_message_preview = _to_message_preview(grpc_chat.last_message_preview)
        return gql_chat

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
        chats = []
        for grpc_chat in grpc_resp.chats:
            gql_chat = from_grpc_chat(grpc_chat)
            if grpc_chat.HasField("last_message_preview"):
                gql_chat.last_message_preview = _to_message_preview(grpc_chat.last_message_preview)
            chats.append(gql_chat)
        return chats

    @strawberry.field
    async def members(
        self,
        chat_id: str,
        info: strawberry.Info[GraphQLContext],
        page: int = 1,
        page_size: int = 50,
    ) -> List[User]:
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
        users = []
        for member in grpc_resp.members:
            grpc_user = await anyio.to_thread.run_sync(
                lambda: info.context.user_client.get_user(member.user_id)
            )
            if grpc_user:
                is_online = await info.context.redis_client.sismember("ws:online_users", grpc_user.user_id)
                grpc_user.is_online = is_online
                users.append(from_grpc_user(grpc_user))
        return users