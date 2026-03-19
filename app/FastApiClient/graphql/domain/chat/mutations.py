import anyio
import strawberry
from typing import List, Optional

from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.utils.converter import from_grpc_chat
from .types import Chat


@strawberry.type
class ChatMutations:
    @strawberry.mutation
    async def create(
        self,
        info: strawberry.Info[GraphQLContext],
        chat_type: str,                    # "private" | "group" | "channel"
        member_ids: List[str],             # UUID строками (для private должен быть 1 собеседник)
        name: Optional[str] = None,
        description: Optional[str] = None,
        avatar_url: Optional[str] = None,
        is_public: bool = False,
        max_members: Optional[int] = None,
    ) -> Chat:
        """
        Реализованная мутация: создаёт чат через gRPC и возвращает GraphQL Chat.
        """
        if not info.context.current_user_id:
            raise PermissionError("Authorization required for create chat")
        
        normalized_member_ids = list(dict.fromkeys(member_ids))
        if not normalized_member_ids:
            raise ValueError("member_ids must not be empty")


        # gRPC stub у тебя синхронный -> чтобы не блокировать event loop, гоняем в thread
        def _call_grpc():
            return info.context.chat_client.create_chat(
                chat_type=chat_type,
                name=name or "",
                description=description or "",
                avatar_url=avatar_url or "",
                is_public=is_public,
                member_ids=normalized_member_ids,
                max_members=max_members,
                access_token=info.context.access_token,
                current_user_id=info.context.current_user_id,
            )

        grpc_chat = await anyio.to_thread.run_sync(_call_grpc)
        print(grpc_chat)
        return from_grpc_chat(grpc_chat)

    @strawberry.mutation
    async def update(
        self,
        info: strawberry.Info[GraphQLContext],
        chat_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        avatar_url: Optional[str] = None,
        is_public: Optional[bool] = None,
        max_members: Optional[int] = None,
    ) -> Chat:
        if not info.context.current_user_id:
            raise PermissionError("Authorization required for update chat")

        def _call_grpc():
            return info.context.chat_client.update_chat(
                chat_id=chat_id,
                name=name,
                description=description,
                avatar_url=avatar_url,
                is_public=is_public,
                max_members=max_members,
                access_token=info.context.access_token,
                current_user_id=info.context.current_user_id,
            )

        return from_grpc_chat(await anyio.to_thread.run_sync(_call_grpc))

    @strawberry.mutation
    async def delete(self, info: strawberry.Info[GraphQLContext], chat_id: str) -> bool:
        if not info.context.current_user_id:
            raise PermissionError("Authorization required for delete chat")

        await anyio.to_thread.run_sync(
            lambda: info.context.chat_client.delete_chat(
                chat_id=chat_id,
                access_token=info.context.access_token,
                current_user_id=info.context.current_user_id,
            )
        )
        return True

    @strawberry.mutation
    async def add_member(
        self,
        info: strawberry.Info[GraphQLContext],
        chat_id: str,
        user_id: str,
        role: str = "member",
    )->bool:
        if not info.context.current_user_id:
            raise PermissionError("Authorization required for add member")

        await anyio.to_thread.run_sync(
            lambda: info.context.chat_client.add_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                role=role,
                access_token=info.context.access_token,
                current_user_id=info.context.current_user_id,
            )
        )
        return True

    @strawberry.mutation
    async def remove_member(
        self,
        info: strawberry.Info[GraphQLContext],
        chat_id: str,
        user_id: str,
    ) -> bool:
        if not info.context.current_user_id:
            raise PermissionError("Authorization required for remove member")

        await anyio.to_thread.run_sync(
            lambda: info.context.chat_client.remove_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                access_token=info.context.access_token,
                current_user_id=info.context.current_user_id,
            )
        )
        return True