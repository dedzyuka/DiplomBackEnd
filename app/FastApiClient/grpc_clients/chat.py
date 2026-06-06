from datetime import datetime
from typing import List, Optional
import grpc

from FastApiClient.core.config import settings
from FastApiClient.protos.protobuf import mess_pb2, mess_pb2_grpc
from .base import BaseGrpcClient


class ChatGrpcClient(BaseGrpcClient):
    def __init__(self):
        super().__init__(settings.CHAT_GRPC_SERVER)
        self.stub = mess_pb2_grpc.ChatServiceStub(self.channel)

    @staticmethod
    def _auth_metadata(access_token: Optional[str], current_user_id: Optional[str] = None):
        if access_token:
            return (("authorization", f"Bearer {access_token}"),)
        return None

    def create_chat(
        self,
        chat_type: str,
        name: str,
        description: str,
        avatar_url: str,
        is_public: bool,
        member_ids: List[str],
        max_members: Optional[int] = None,
        access_token: Optional[str] = None,
        current_user_id: Optional[str] = None,
    ) -> mess_pb2.Chat:
        chat_type_map = {
            "private": mess_pb2.PRIVATE,
            "group": mess_pb2.GROUP,
            "channel": mess_pb2.CHANNEL,
        }
        ct = chat_type_map.get((chat_type or "").lower())
        if ct is None:
            raise ValueError("chat_type must be one of: private, group, channel")

        req_kwargs = dict(
            chat_type=ct,
            name=name,
            description=description,
            avatar_url=avatar_url,
            is_public=is_public,
            member_ids=list(member_ids),
        )
        if max_members is not None:
            req_kwargs["max_members"] = int(max_members)

        request = mess_pb2.CreateChatRequest(**req_kwargs)

        try:
            return self.stub.CreateChat(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token, current_user_id),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def get_chat(self, chat_id: str, access_token: Optional[str] = None, current_user_id: Optional[str] = None) -> mess_pb2.Chat:
        try:
            return self.stub.GetChat(
                mess_pb2.GetChatRequest(chat_id=chat_id),
                timeout=5,
                metadata=self._auth_metadata(access_token, current_user_id),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def list_chats(self, user_id: str, page: int = 1, page_size: int = 20,
                   access_token: Optional[str] = None, current_user_id: Optional[str] = None):
        page = max(1, page)
        page_size = max(1, page_size)
        request = mess_pb2.ListChatsRequest(user_id=user_id, page_size=page_size, page_token=str((page - 1) * page_size))
        try:
            return self.stub.ListChats(request, timeout=5, metadata=self._auth_metadata(access_token, current_user_id))
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def update_chat(self, chat_id: str, name: Optional[str] = None, description: Optional[str] = None,
                    avatar_url: Optional[str] = None, is_public: Optional[bool] = None,
                    max_members: Optional[int] = None, access_token: Optional[str] = None,
                    current_user_id: Optional[str] = None) -> mess_pb2.Chat:
        req_kwargs = {"chat_id": chat_id}
        if name is not None:
            req_kwargs["name"] = name
        if description is not None:
            req_kwargs["description"] = description
        if avatar_url is not None:
            req_kwargs["avatar_url"] = avatar_url
        if is_public is not None:
            req_kwargs["is_public"] = is_public
        if max_members is not None:
            req_kwargs["max_members"] = int(max_members)

        try:
            return self.stub.UpdateChat(
                mess_pb2.UpdateChatRequest(**req_kwargs),
                timeout=5,
                metadata=self._auth_metadata(access_token, current_user_id),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def delete_chat(self, chat_id: str, access_token: Optional[str] = None, current_user_id: Optional[str] = None) -> None:
        try:
            self.stub.DeleteChat(
                mess_pb2.DeleteChatRequest(chat_id=chat_id),
                timeout=5,
                metadata=self._auth_metadata(access_token, current_user_id),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def add_chat_member(self, chat_id: str, user_id: str, role: str = "member",
                        access_token: Optional[str] = None, current_user_id: Optional[str] = None):
        role_map = {"owner": mess_pb2.OWNER, "admin": mess_pb2.ADMIN, "member": mess_pb2.MEMBER}
        try:
            return self.stub.AddChatMember(
                mess_pb2.AddChatMemberRequest(chat_id=chat_id, user_id=user_id, role=role_map.get(role.lower(), mess_pb2.MEMBER)),
                timeout=5,
                metadata=self._auth_metadata(access_token, current_user_id),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def generate_invite_link(self, chat_id: str, access_token: Optional[str] = None, current_user_id: Optional[str] = None):
        request = mess_pb2.GenerateInviteLinkRequest(chat_id=chat_id)
        try:
            return self.stub.GenerateInviteLink(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token, current_user_id),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def join_chat_with_token(self, invite_token: str, access_token: Optional[str] = None, current_user_id: Optional[str] = None):
        """Вступление в чат по invite токену (через JoinChatRequest с заполненным invite_token)"""
        # Протокол требует chat_id и user_id, но на сервере они будут переопределены по токену
        request = mess_pb2.JoinChatRequest(
            chat_id="",
            user_id="",
            invite_token=invite_token
        )
        try:
            return self.stub.JoinChat(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token, current_user_id),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def update_chat_member(self, chat_id: str, user_id: str, role: Optional[str] = None,
                           status: Optional[str] = None, banned_until: Optional[str] = None,
                           access_token: Optional[str] = None, current_user_id: Optional[str] = None):
        req = mess_pb2.UpdateChatMemberRequest(chat_id=chat_id, user_id=user_id)
        if role is not None:
            role_map = {"owner": mess_pb2.OWNER, "admin": mess_pb2.ADMIN, "member": mess_pb2.MEMBER}
            req.role = role_map.get(role.lower(), mess_pb2.MEMBER)
        if status is not None:
            status_map = {"active": mess_pb2.ACTIVE_N, "left": mess_pb2.LEFT, "banned": mess_pb2.BANNED}
            req.status = status_map.get(status.lower(), mess_pb2.ACTIVE_N)
        if banned_until is not None:
            # парсим ISO строку в Timestamp
            dt = datetime.fromisoformat(banned_until.replace('Z', '+00:00'))
            req.banned_until.FromDatetime(dt)
        try:
            return self.stub.UpdateChatMember(req, timeout=5, metadata=self._auth_metadata(access_token, current_user_id))
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def kick_member(self, chat_id: str, user_id: str, access_token: Optional[str] = None, current_user_id: Optional[str] = None):
        return self.stub.KickMember(mess_pb2.KickMemberRequest(chat_id=chat_id, user_id=user_id),
                                    timeout=5, metadata=self._auth_metadata(access_token, current_user_id))

    def ban_member(self, chat_id: str, user_id: str, banned_until: Optional[str] = None,
                   access_token: Optional[str] = None, current_user_id: Optional[str] = None):
        req = mess_pb2.BanMemberRequest(chat_id=chat_id, user_id=user_id)
        if banned_until:
            dt = datetime.fromisoformat(banned_until.replace('Z', '+00:00'))
            req.banned_until.FromDatetime(dt)
        return self.stub.BanMember(req, timeout=5, metadata=self._auth_metadata(access_token, current_user_id))

    def unban_member(self, chat_id: str, user_id: str, access_token: Optional[str] = None, current_user_id: Optional[str] = None):
        return self.stub.UnbanMember(mess_pb2.UnbanMemberRequest(chat_id=chat_id, user_id=user_id),
                                     timeout=5, metadata=self._auth_metadata(access_token, current_user_id))

    def leave_chat(self, chat_id: str, user_id: str, access_token: Optional[str] = None, current_user_id: Optional[str] = None):
        return self.stub.LeaveChat(mess_pb2.LeaveChatRequest(chat_id=chat_id, user_id=user_id),
                                   timeout=5, metadata=self._auth_metadata(access_token, current_user_id))

    def remove_chat_member(self, chat_id: str, user_id: str, access_token: Optional[str] = None,
                           current_user_id: Optional[str] = None) -> None:
        try:
            self.stub.RemoveChatMember(
                mess_pb2.RemoveChatMemberRequest(chat_id=chat_id, user_id=user_id),
                timeout=5,
                metadata=self._auth_metadata(access_token, current_user_id),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def list_chat_members(self, chat_id: str, page: int = 1, page_size: int = 50,
                          access_token: Optional[str] = None, current_user_id: Optional[str] = None):
        page = max(1, page)
        page_size = max(1, page_size)
        try:
            return self.stub.ListChatMembers(
                mess_pb2.ListChatMembersRequest(chat_id=chat_id, page_size=page_size, page_token=str((page - 1) * page_size)),
                timeout=5,
                metadata=self._auth_metadata(access_token, current_user_id),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)