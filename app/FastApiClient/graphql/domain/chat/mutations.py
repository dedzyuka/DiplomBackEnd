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
        chat_type: str,
        member_ids: List[str],
        name: Optional[str] = None,
        description: Optional[str] = None,
        avatar_url: Optional[str] = None,
        is_public: bool = False,
        max_members: Optional[int] = None,
    ) -> Chat:
        current_user_id = info.context.require_user_id()
        access_token = info.context.require_access_token()

        normalized_member_ids = list(dict.fromkeys(member_ids))
        if not normalized_member_ids:
            raise ValueError("member_ids must not be empty")

        def _call_grpc():
            return info.context.chat_client.create_chat(
                chat_type=chat_type,
                name=name or "",
                description=description or "",
                avatar_url=avatar_url or "",
                is_public=is_public,
                member_ids=normalized_member_ids,
                max_members=max_members,
                access_token=access_token,
                current_user_id=current_user_id,
            )

        grpc_chat = await anyio.to_thread.run_sync(_call_grpc)
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
        current_user_id = info.context.require_user_id()
        access_token = info.context.require_access_token()

        def _call_grpc():
            return info.context.chat_client.update_chat(
                chat_id=chat_id,
                name=name,
                description=description,
                avatar_url=avatar_url,
                is_public=is_public,
                max_members=max_members,
                access_token=access_token,
                current_user_id=current_user_id,
            )

        return from_grpc_chat(await anyio.to_thread.run_sync(_call_grpc))

    @strawberry.mutation
    async def delete(self, info: strawberry.Info[GraphQLContext], chat_id: str) -> bool:
        current_user_id = info.context.require_user_id()
        access_token = info.context.require_access_token()

        await anyio.to_thread.run_sync(
            lambda: info.context.chat_client.delete_chat(
                chat_id=chat_id,
                access_token=access_token,
                current_user_id=current_user_id,
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
    ) -> bool:
        current_user_id = info.context.require_user_id()
        access_token = info.context.require_access_token()

        await anyio.to_thread.run_sync(
            lambda: info.context.chat_client.add_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                role=role,
                access_token=access_token,
                current_user_id=current_user_id,
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
        current_user_id = info.context.require_user_id()
        access_token = info.context.require_access_token()

        await anyio.to_thread.run_sync(
            lambda: info.context.chat_client.remove_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                access_token=access_token,
                current_user_id=current_user_id,
            )
        )
        return True
    
    @strawberry.mutation
    async def generate_invite_link(self, info: strawberry.Info[GraphQLContext], chat_id: str) -> str:
        """Возвращает invite_key (токен) для приглашения в чат."""
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            resp = info.context.chat_client.generate_invite_link(
                chat_id=chat_id, access_token=access_token, current_user_id=current_user_id
            )
            return resp.invite_key
        return await anyio.to_thread.run_sync(_call)

    @strawberry.mutation
    async def join_chat_with_token(self, info: strawberry.Info[GraphQLContext], invite_token: str) -> bool:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            info.context.chat_client.join_chat_with_token(
                invite_token=invite_token, access_token=access_token, current_user_id=current_user_id
            )
            return True
        return await anyio.to_thread.run_sync(_call)

    @strawberry.mutation
    async def update_chat_member(
        self,
        info: strawberry.Info[GraphQLContext],
        chat_id: str,
        user_id: str,
        role: Optional[str] = None,
        status: Optional[str] = None,
        banned_until: Optional[str] = None,
    ) -> bool:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            info.context.chat_client.update_chat_member(
                chat_id=chat_id, user_id=user_id, role=role, status=status, banned_until=banned_until,
                access_token=access_token, current_user_id=current_user_id
            )
            return True
        return await anyio.to_thread.run_sync(_call)

    @strawberry.mutation
    async def kick_member(
        self,
        info: strawberry.Info[GraphQLContext],
        chat_id: str,
        user_id: str,
    ) -> bool:
        """Исключить участника из группы (требует прав админа/владельца)."""
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            info.context.chat_client.kick_member(
                chat_id=chat_id,
                user_id=user_id,
                access_token=access_token,
                current_user_id=current_user_id,
            )
            return True
        return await anyio.to_thread.run_sync(_call)

    @strawberry.mutation
    async def ban_member(
        self,
        info: strawberry.Info[GraphQLContext],
        chat_id: str,
        user_id: str,
        banned_until: Optional[str] = None,
    ) -> bool:
        """Забанить участника (требует прав админа/владельца)."""
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            info.context.chat_client.ban_member(
                chat_id=chat_id,
                user_id=user_id,
                banned_until=banned_until,
                access_token=access_token,
                current_user_id=current_user_id,
            )
            return True
        return await anyio.to_thread.run_sync(_call)

    @strawberry.mutation
    async def unban_member(
        self,
        info: strawberry.Info[GraphQLContext],
        chat_id: str,
        user_id: str,
    ) -> bool:
        """Разбанить участника (требует прав админа/владельца)."""
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            info.context.chat_client.unban_member(
                chat_id=chat_id,
                user_id=user_id,
                access_token=access_token,
                current_user_id=current_user_id,
            )
            return True
        return await anyio.to_thread.run_sync(_call)

    @strawberry.mutation
    async def leave_chat(
        self,
        info: strawberry.Info[GraphQLContext],
        chat_id: str,
    ) -> bool:
        """Выйти из чата (текущий пользователь покидает чат)."""
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            info.context.chat_client.leave_chat(
                chat_id=chat_id,
                user_id=current_user_id,
                access_token=access_token,
                current_user_id=current_user_id,
            )
            return True
        return await anyio.to_thread.run_sync(_call)

    @strawberry.mutation
    async def update_chat(
        self,
        info: strawberry.Info[GraphQLContext],
        chat_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        avatar_url: Optional[str] = None,
        is_public: Optional[bool] = None,
        max_members: Optional[int] = None,
    ) -> Chat:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            grpc_chat = info.context.chat_client.update_chat(
                chat_id=chat_id, name=name, description=description, avatar_url=avatar_url,
                is_public=is_public, max_members=max_members,
                access_token=access_token, current_user_id=current_user_id
            )
            return from_grpc_chat(grpc_chat)
        return await anyio.to_thread.run_sync(_call)
    
    @strawberry.mutation
    async def join_chat(self, info: strawberry.Info[GraphQLContext], invite_token: str) -> bool:
        """Вступить в чат по инвайт-токену."""
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            info.context.chat_client.join_chat_with_token(
                invite_token=invite_token,
                access_token=access_token,
                current_user_id=current_user_id,
            )
            return True
        return await anyio.to_thread.run_sync(_call)