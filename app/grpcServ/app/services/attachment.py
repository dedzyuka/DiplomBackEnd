import uuid
import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator
import grpc
from google.protobuf.empty_pb2 import Empty
from sqlalchemy import func, select

from database import AsyncSessionLocal
from protobuf import mess_pb2, mess_pb2_grpc
from services.minio_client import MinioClient
from services.models import Attachment
from services.access_session import require_current_user_uuid

minio_client = MinioClient()

class AttachmentServicer(mess_pb2_grpc.AttachmentServiceServicer):
    async def UploadAttachment(self, request_iterator, context):
        # Получаем текущего пользователя (для аудита, но не обязателен)
        user_id = await require_current_user_uuid(context)
        metadata = None
        chunks = []
        async for req in request_iterator:
            if req.HasField("metadata"):
                metadata = req.metadata
            elif req.HasField("chunk"):
                chunks.append(req.chunk)
        if not metadata:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Missing metadata")

        # Проверка размера (5 MB)
        total_size = sum(len(chunk) for chunk in chunks)
        if total_size > 5 * 1024 * 1024:
            await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "File too large (max 5MB)")

        # Генерация уникального имени
        ext = metadata.file_name.split('.')[-1] if '.' in metadata.file_name else ''
        object_name = f"attachments/{uuid.uuid4()}.{ext}" if ext else f"attachments/{uuid.uuid4()}"
        file_bytes = b''.join(chunks)
        content_type = metadata.mime_type or "application/octet-stream"

        # Загружаем в MinIO
        try:
            await minio_client.upload_file(file_bytes, object_name, content_type)
        except Exception as e:
            await context.abort(grpc.StatusCode.INTERNAL, f"Failed to upload: {e}")

        # Сохраняем в БД
        async with AsyncSessionLocal() as session:
            attachment = Attachment(
                attachment_id=uuid.uuid4(),
                message_id=None,  # временно, будет обновлено при привязке к сообщению
                message_created_at=datetime.now(timezone.utc),
                file_name=metadata.file_name,
                file_size=total_size,
                mime_type=content_type,
                storage_path=object_name,
                uploaded_at=datetime.now(timezone.utc)
            )
            session.add(attachment)
            await session.commit()
            await session.refresh(attachment)

        return mess_pb2.UploadAttachmentResponse(
            attachment_id=str(attachment.attachment_id),
            storage_path=object_name)       

    async def GetAttachment(self, request, context):
        user_id = await require_current_user_uuid(context)  # авторизация
        attachment_id = request.attachment_id
        async with AsyncSessionLocal() as session:
            attachment = await session.get(Attachment, uuid.UUID(attachment_id))
            if not attachment:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Attachment not found")
            # Генерируем presigned URL
            url = await minio_client.get_presigned_url(attachment.storage_path)
            resp = mess_pb2.Attachment(
                attachment_id=str(attachment.attachment_id),
                message_id=attachment.message_id,
                file_name=attachment.file_name,
                file_size=attachment.file_size or 0,
                mime_type=attachment.mime_type or "",
                storage_path=url,
            )
            # timestamps
            if attachment.uploaded_at:
                resp.uploaded_at.FromDatetime(attachment.uploaded_at)
            return resp

    async def ListAttachments(self, request, context):
        user_id = await require_current_user_uuid(context)
        message_id = request.message_id
        page_size = max(1, min(request.page_size or 20, 100))
        try:
            offset = int(request.page_token) if request.page_token else 0
        except:
            offset = 0

        async with AsyncSessionLocal() as session:
            query = select(Attachment).where(Attachment.message_id == message_id)
            total = await session.scalar(select(func.count()).select_from(query.subquery()))
            attachments = (await session.execute(query.offset(offset).limit(page_size))).scalars().all()
            next_token = str(offset + page_size) if offset + page_size < total else ""
            response = mess_pb2.AttachmentsListResponse(
                attachments=[self._to_proto(a) for a in attachments],
                next_page_token=next_token,
                total_count=total or 0
            )
            return response

    def _to_proto(self, attachment: Attachment) -> mess_pb2.Attachment:
        pb = mess_pb2.Attachment(
            attachment_id=str(attachment.attachment_id),
            message_id=attachment.message_id,
            file_name=attachment.file_name,
            file_size=attachment.file_size or 0,
            mime_type=attachment.mime_type or "",
            storage_path=attachment.storage_path,
        )
        if attachment.uploaded_at:
            pb.uploaded_at.FromDatetime(attachment.uploaded_at)
        if attachment.message_created_at:
            pb.message_created_at.FromDatetime(attachment.message_created_at)
        return pb