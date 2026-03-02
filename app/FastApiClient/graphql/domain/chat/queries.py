import strawberry
from typing import List, Optional

from FastApiClient.graphql.context import GraphQLContext
from .types import Chat


@strawberry.type
class ChatQueries:
    @strawberry.field
    async def get(self, chat_id: str, info: strawberry.Info[GraphQLContext]) -> Chat:
        # TODO: call info.context.chat_client.get_chat(...)
        pass

    @strawberry.field
    async def list(
        self,
        info: strawberry.Info[GraphQLContext],
        page: int = 1,
        page_size: int = 20,
    ) -> List[Chat]:
        # TODO: call info.context.chat_client.list_chats(...)
        pass

    @strawberry.field
    async def members(
        self,
        chat_id: str,
        info: strawberry.Info[GraphQLContext],
        page: int = 1,
        page_size: int = 50,
    ):
        # TODO: call info.context.chat_client.list_chat_members(...)
        pass