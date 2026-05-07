import grpc

from FastApiClient.core.config import settings
from FastApiClient.protos.protobuf import mess_pb2, mess_pb2_grpc

from .base import BaseGrpcClient


class ContactGrpcClient(BaseGrpcClient):
    def __init__(self):
        super().__init__(settings.USER_GRPC_SERVER)
        self.stub = mess_pb2_grpc.ContactServiceStub(self.channel)

    @staticmethod
    def _auth_metadata(access_token: str | None):
        if access_token:
            return (("authorization", f"Bearer {access_token}"),)
        return None

    def add_contact(
        self,
        *,
        user_id: str,
        contact_user_id: str,
        access_token: str,
    ) -> mess_pb2.Contact:
        request = mess_pb2.AddContactRequest(
            user_id=user_id,
            contact_user_id=contact_user_id,
        )

        try:
            return self.stub.AddContact(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def accept_contact(
        self,
        *,
        user_id: str,
        contact_user_id: str,
        access_token: str,
    ) -> mess_pb2.Contact:
        request = mess_pb2.AcceptContactRequest(
            user_id=user_id,
            contact_user_id=contact_user_id,
        )

        try:
            return self.stub.AcceptContact(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def block_contact(
        self,
        *,
        user_id: str,
        contact_user_id: str,
        access_token: str,
    ) -> mess_pb2.Contact:
        request = mess_pb2.BlockContactRequest(
            user_id=user_id,
            contact_user_id=contact_user_id,
        )

        try:
            return self.stub.BlockContact(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def remove_contact(
        self,
        *,
        user_id: str,
        contact_user_id: str,
        access_token: str,
    ) -> None:
        request = mess_pb2.RemoveContactRequest(
            user_id=user_id,
            contact_user_id=contact_user_id,
        )

        try:
            self.stub.RemoveContact(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)

    def list_contacts(
        self,
        *,
        user_id: str,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
        access_token: str,
    ) -> mess_pb2.ContactsListResponse:
        status_map = {
            None: 0,
            "pending": mess_pb2.ContactStatus.PENDING,
            "accepted": mess_pb2.ContactStatus.ACCEPTED,
            "blocked": mess_pb2.ContactStatus.BLOCKED,
        }

        page = max(page, 1)
        page_size = max(1, min(page_size, 100))
        page_token = str((page - 1) * page_size)

        request = mess_pb2.ListContactsRequest(
            user_id=user_id,
            status=status_map.get(status, 0),
            page_size=page_size,
            page_token=page_token,
        )

        try:
            return self.stub.ListContacts(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)
    def list_incoming_contacts(
        self,
        *,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        access_token: str,
    ) -> mess_pb2.ContactsListResponse:
        page = max(page, 1)
        page_size = max(1, min(page_size, 100))
        page_token = str((page - 1) * page_size)

        request = mess_pb2.ListContactsRequest(
            user_id=user_id,
            status=mess_pb2.ContactStatus.PENDING,
            page_size=page_size,
            page_token=page_token,
        )

        try:
            return self.stub.ListIncomingContacts(
                request,
                timeout=5,
                metadata=self._auth_metadata(access_token),
            )
        except grpc.RpcError as e:
            self._handle_rpc_error(e)