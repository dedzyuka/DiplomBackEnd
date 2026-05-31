import grpc
from typing import List, Optional

from FastApiClient.core.config import settings
from FastApiClient.protos.protobuf import mess_pb2, mess_pb2_grpc
from .base import BaseGrpcClient


class MessageGrpcClient(BaseGrpcClient):
    def __init__(self):
        super().__init__(settings.CHAT_GRPC_SERVER)
        self.stub = mess_pb2_grpc.MessageServiceStub(self.channel)

    @staticmethod
    def _auth_metadata(access_token: Optional[str]):
        if access_token:
            return (("authorization", f"Bearer {access_token}"),)
        return None

    def send_message(
    self,
    chat_id: str,
    content: str,
    sender_id: str,
    reply_to_id: Optional[int] = None,
    type: int = mess_pb2.TEXT,
    attachments: Optional[List[dict]] = None,
    mentions: Optional[List[str]] = None,
    access_token: Optional[str] = None,
) -> mess_pb2.Message:
        req_kwargs = {
            "chat_id": chat_id,
            "sender_id": sender_id,
            "content": content,
            "type": type,
        }
        if reply_to_id is not None:
            req_kwargs["reply_to_id"] = reply_to_id
        if attachments:
            for att in attachments:
                att_input = req_kwargs.setdefault("attachments", []).append(
                    mess_pb2.AttachmentInput(attachment_id=att.get("attachment_id"))
                )
        if mentions:
            req_kwargs["mentions"] = mentions

        request = mess_pb2.SendMessageRequest(**req_kwargs)
        try:
            return self.stub.SendMessage(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def get_message(self, message_id: int, chat_id: str, access_token: Optional[str] = None) -> mess_pb2.Message:
        request = mess_pb2.GetMessageRequest(message_id=message_id, chat_id=chat_id)
        try:
            return self.stub.GetMessage(request, timeout=5, metadata=self._auth_metadata(access_token))
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def list_messages(self, chat_id: str, page: int = 1, page_size: int = 50,
                      access_token: Optional[str] = None) -> mess_pb2.MessagesListResponse:
        page_token = str((page - 1) * page_size) if page > 1 else ""
        request = mess_pb2.ListMessagesRequest(
            chat_id=chat_id,
            page_size=page_size,
            page_token=page_token,
        )
        try:
            return self.stub.ListMessages(request, timeout=5, metadata=self._auth_metadata(access_token))
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def update_message(self, message_id: int, chat_id: str, content: str,
                       access_token: Optional[str] = None) -> mess_pb2.Message:
        request = mess_pb2.UpdateMessageRequest(
            message_id=message_id,
            chat_id=chat_id,
            content=content,
        )
        try:
            return self.stub.UpdateMessage(request, timeout=5, metadata=self._auth_metadata(access_token))
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def delete_message(self, message_id: int, chat_id: str, access_token: Optional[str] = None) -> None:
        request = mess_pb2.DeleteMessageRequest(message_id=message_id, chat_id=chat_id)
        try:
            self.stub.DeleteMessage(request, timeout=5, metadata=self._auth_metadata(access_token))
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def add_reaction(self, message_id: int, chat_id: str, emoji: str, access_token: Optional[str] = None) -> mess_pb2.Reaction:
        request = mess_pb2.AddReactionRequest(
            message_id=message_id,
            chat_id=chat_id,
            user_id="",  # будет заменён на сервере
            emoji=emoji,
        )
        try:
            return self.stub.AddReaction(request, timeout=5, metadata=self._auth_metadata(access_token))
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def remove_reaction(self, message_id: int, chat_id: str, emoji: str, access_token: Optional[str] = None) -> None:
        request = mess_pb2.RemoveReactionRequest(
            message_id=message_id,
            chat_id=chat_id,
            user_id="",
            emoji=emoji,
        )
        try:
            self.stub.RemoveReaction(request, timeout=5, metadata=self._auth_metadata(access_token))
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def mark_as_delivered(self, message_id: int, chat_id: str, access_token: Optional[str] = None):
        request = mess_pb2.MarkAsDeliveredRequest(message_id=message_id, chat_id=chat_id)
        try:
            return self.stub.MarkAsDelivered(request, timeout=5, metadata=self._auth_metadata(access_token))
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def mark_as_read(self, message_id: int, chat_id: str, access_token: Optional[str] = None):
        request = mess_pb2.MarkAsReadRequest(message_id=message_id, chat_id=chat_id)
        try:
            return self.stub.MarkAsRead(request, timeout=5, metadata=self._auth_metadata(access_token))
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def search_messages(self, chat_id: str, query: str, page: int = 1, page_size: int = 50,
                        access_token: Optional[str] = None) -> mess_pb2.MessagesListResponse:
        request = mess_pb2.SearchMessagesRequest(
            chat_id=chat_id,
            query=query,
            page=page,
            page_size=page_size,
        )
        try:
            return self.stub.SearchMessages(request, timeout=5, metadata=self._auth_metadata(access_token))
        except grpc.RpcError as e:
            self._handle_rpc_error(e)