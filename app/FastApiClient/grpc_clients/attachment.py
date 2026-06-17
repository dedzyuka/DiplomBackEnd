import grpc
from typing import Iterator
from FastApiClient.core.config import settings
from FastApiClient.protos.protobuf import mess_pb2, mess_pb2_grpc
from FastApiClient.grpc_clients.base import BaseGrpcClient


class AttachmentGrpcClient(BaseGrpcClient):
    def __init__(self) -> None:
        super().__init__(settings.ATTACHMENT_GRPC_SERVER)
        self.channel = grpc.insecure_channel(settings.ATTACHMENT_GRPC_SERVER)
        self.stub = mess_pb2_grpc.AttachmentServiceStub(self.channel)

    def _auth_metadata(self, access_token: str):
        return (("authorization", f"Bearer {access_token}"),)

    def upload_attachment(self, file_name: str, mime_type: str, file_data: bytes, access_token: str):
        def generate() -> Iterator[mess_pb2.UploadAttachmentRequest]:
            # Сначала metadata
            yield mess_pb2.UploadAttachmentRequest(
                metadata=mess_pb2.AttachmentInput(
                    file_name=file_name,
                    mime_type=mime_type,
                    file_size=len(file_data),
                    storage_path=""  # будет заполнено на сервере
                )
            )
            # Чанками по 1MB
            chunk_size = 1024 * 1024
            for i in range(0, len(file_data), chunk_size):
                chunk = file_data[i:i+chunk_size]
                yield mess_pb2.UploadAttachmentRequest(chunk=chunk)

        metadata = self._auth_metadata(access_token)
        response = self.stub.UploadAttachment(generate(), metadata=metadata)
        return response