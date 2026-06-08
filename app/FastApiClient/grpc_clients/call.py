import grpc
from FastApiClient.core.config import settings
from FastApiClient.protos.protobuf import mess_pb2, mess_pb2_grpc
from .base import BaseGrpcClient

class CallGrpcClient(BaseGrpcClient):
    def __init__(self):
        super().__init__(settings.CALL_GRPC_SERVER)
        self.stub = mess_pb2_grpc.CallServiceStub(self.channel)

    @staticmethod
    def _auth_metadata(access_token: str | None, current_user_id: str | None = None):
        if access_token:
            return (("authorization", f"Bearer {access_token}"),)
        return None

    def start_call(self, chat_id: str, type: str, access_token: str, current_user_id: str) -> mess_pb2.CallInfo:
        return self.stub.StartCall(
            mess_pb2.StartCallRequest(chat_id=chat_id, type=type),
            metadata=self._auth_metadata(access_token, current_user_id),
        )

    def accept_call(self, call_id: str, access_token: str, current_user_id: str) -> mess_pb2.CallInfo:
        return self.stub.AcceptCall(
            mess_pb2.AcceptCallRequest(call_id=call_id),
            metadata=self._auth_metadata(access_token, current_user_id),
        )

    def reject_call(self, call_id: str, access_token: str, current_user_id: str) -> None:
        self.stub.RejectCall(
            mess_pb2.RejectCallRequest(call_id=call_id),
            metadata=self._auth_metadata(access_token, current_user_id),
        )

    def end_call(self, call_id: str, access_token: str, current_user_id: str) -> None:
        self.stub.EndCall(
            mess_pb2.EndCallRequest(call_id=call_id),
            metadata=self._auth_metadata(access_token, current_user_id),
        )

    def get_call(self, call_id: str, access_token: str, current_user_id: str) -> mess_pb2.CallInfo:
        return self.stub.GetCall(
            mess_pb2.GetCallRequest(call_id=call_id),
            metadata=self._auth_metadata(access_token, current_user_id),
        )

    def list_calls(self, chat_id: str, page: int, page_size: int, access_token: str, current_user_id: str) -> mess_pb2.CallsListResponse:
        return self.stub.ListCalls(
            mess_pb2.ListCallsRequest(chat_id=chat_id, page=page, page_size=page_size),
            metadata=self._auth_metadata(access_token, current_user_id),
        )

    def get_livekit_token(self, call_id: str, access_token: str):
        request = mess_pb2.LiveKitTokenRequest(call_id=call_id, user_id="")
        return self.stub.GetLiveKitToken(request, metadata=self._auth_metadata(access_token))