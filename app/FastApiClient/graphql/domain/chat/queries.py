import anyio
import strawberry
from typing import List, Optional

from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.graphql.domain.user.types import User
from FastApiClient.graphql.domain.chat.types import Chat, MessagePreview, ChatMember
from FastApiClient.utils.converter import from_grpc_chat, _ts_to_iso, from_grpc_user
from FastApiClient.protos.protobuf import mess_pb2


def _to_message_preview(grpc_preview):
    if not grpc_preview:
        return None
    return MessagePreview(
        message_id=grpc_preview.message_id,
        sender_id=grpc_preview.sender_id,
        sender_nickname=None,
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
        # Преобразуем grpc_chat в Chat с my_role
        gql_chat = from_grpc_chat(grpc_chat)
        if grpc_chat.HasField("last_message_preview"):
            gql_chat.last_message_preview = _to_message_preview(grpc_chat.last_message_preview)
        if grpc_chat.my_role != 0:
            role_map = {1: "owner", 2: "admin", 3: "member"}
            gql_chat.my_role = role_map.get(grpc_chat.my_role, "member")
        if grpc_chat.join_policy != 0:
            policy_map = {1: "invite_only", 2: "request_approval", 3: "open"}
            gql_chat.join_policy = policy_map.get(grpc_chat.join_policy, "invite_only")
        
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
            if grpc_chat.my_role != 0:
                role_map = {1: "owner", 2: "admin", 3: "member"}
                gql_chat.my_role = role_map.get(grpc_chat.my_role, "member")
            if grpc_chat.join_policy != 0:
                policy_map = {1: "invite_only", 2: "request_approval", 3: "open"}
                gql_chat.join_policy = policy_map.get(grpc_chat.join_policy, "invite_only")
            chats.append(gql_chat)
        return chats

    @strawberry.field
    async def members(
        self,
        chat_id: str,
        info: strawberry.Info[GraphQLContext],
        page: int = 1,
        page_size: int = 50,
    ) -> List[ChatMember]:
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
        result = []
        for grpc_member in grpc_resp.members:
            # Конвертируем пользователя
            grpc_user = grpc_member.user
            user = from_grpc_user(grpc_user)
            # Роль
            role_map = {
                mess_pb2.OWNER: "owner",
                mess_pb2.ADMIN: "admin",
                mess_pb2.MEMBER: "member",
                mess_pb2.MEMBER_ROLE_UNSPECIFIED: "member",
            }
            role = role_map.get(grpc_member.role, "member")
            # Статус
            status_map = {
                mess_pb2.ACTIVE_N: "active",
                mess_pb2.LEFT: "left",
                mess_pb2.BANNED: "banned",
                mess_pb2.MEMBER_STATUS_UNSPECIFIED: "active",
            }
            status = status_map.get(grpc_member.status, "active")
            
            chat_member = ChatMember(
                user=user,
                role=role,
                status=status,
                joined_at=_ts_to_iso(grpc_member.joined_at),
                left_at=_ts_to_iso(grpc_member.left_at) if grpc_member.HasField("left_at") else None,
                banned_until=_ts_to_iso(grpc_member.banned_until) if grpc_member.HasField("banned_until") else None,
            )
            result.append(chat_member)
        return result
    

    @strawberry.field
    async def generate_invite_link(self, info: strawberry.Info[GraphQLContext], chat_id: str) -> str:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            resp = info.context.chat_client.generate_invite_link(
                chat_id=chat_id,
                access_token=access_token,
                current_user_id=current_user_id,
            )
            return resp.invite_key
        return await anyio.to_thread.run_sync(_call)