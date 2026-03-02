from typing import List, Optional
import grpc

from FastApiClient.core.config import settings
from FastApiClient.protos.protobuf import mess_pb2, mess_pb2_grpc
from .base import BaseGrpcClient


class ChatGrpcClient(BaseGrpcClient):
    def __init__(self):
        super().__init__(settings.USER_GRPC_SERVER)
        self.stub = mess_pb2_grpc.ChatServiceStub(self.channel)

    @staticmethod
    def _auth_metadata(access_token: Optional[str]):
        if access_token:
            return (("authorization", f"Bearer {access_token}"),)
        return None

    # ---- реализовано ----
    def create_chat(
        self,
        chat_type: str,                 # "private" | "group" | "channel"
        name: str,
        description: str,
        avatar_url: str,
        is_public: bool,
        member_ids: List[str],
        max_members: Optional[int] = None,
        access_token: Optional[str] = None,
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
                metadata=self._auth_metadata(access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    # ---- остальное: pass ----
    def get_chat(self, chat_id: str, access_token: Optional[str] = None) -> mess_pb2.Chat:
        pass

    def list_chats(self, page: int = 1, page_size: int = 20, access_token: Optional[str] = None):
        pass

    def update_chat(self, chat_id: str, name: Optional[str] = None, description: Optional[str] = None,
                    avatar_url: Optional[str] = None, is_public: Optional[bool] = None,
                    max_members: Optional[int] = None, access_token: Optional[str] = None) -> mess_pb2.Chat:
        pass

    def delete_chat(self, chat_id: str, access_token: Optional[str] = None) -> None:
        pass

    def add_chat_member(self, chat_id: str, user_id: str, role: str = "member",
                        access_token: Optional[str] = None):
        pass

    def remove_chat_member(self, chat_id: str, user_id: str, access_token: Optional[str] = None) -> None:
        pass

    def list_chat_members(self, chat_id: str, page: int = 1, page_size: int = 50,
                          access_token: Optional[str] = None):
        pass