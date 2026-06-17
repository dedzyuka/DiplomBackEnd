import base64
import json
import os
import tempfile
import ffmpeg
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
from services.models import Attachments as Attachment
from services.access_session import require_current_user_uuid

minio_client = MinioClient()

class AttachmentServicer(mess_pb2_grpc.AttachmentServiceServicer):
    async def UploadAttachment(self, request_iterator, context):
        # Получаем текущего пользователя
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

        total_size = sum(len(chunk) for chunk in chunks)
        if total_size > 5 * 1024 * 1024:
            await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "File too large (max 5MB)")

        attachment_id = uuid.uuid4()
        ext = metadata.file_name.split('.')[-1] if '.' in metadata.file_name else ''
        object_name = f"attachments/{attachment_id}.{ext}" if ext else f"attachments/{attachment_id}"
        file_bytes = b''.join(chunks)
        content_type = metadata.mime_type or "application/octet-stream"

        # Загружаем в MinIO
        try:
            await minio_client.upload_file(file_bytes, object_name, content_type)
        except Exception as e:
            await context.abort(grpc.StatusCode.INTERNAL, f"Failed to upload: {e}")

        # Извлечение метаданных для аудио/видео
        duration = None
        waveform = None
        thumbnail_url = None
        is_circular = metadata.is_circular if metadata.HasField("is_circular") else False

        if content_type.startswith('audio/') or content_type.startswith('video/'):
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            try:
                # длительность
                probe = ffmpeg.probe(tmp_path)
                duration = int(float(probe['format']['duration']))
                
                if content_type.startswith('video/'):
                    # извлечь thumbnail (первый кадр на 1 секунде)
                    thumb_path = tmp_path + '_thumb.jpg'
                    ffmpeg.input(tmp_path, ss=1).output(thumb_path, vframes=1).run()
                    with open(thumb_path, 'rb') as f:
                        thumb_data = f.read()
                    thumb_object_name = f"thumbnails/{attachment_id}.jpg"
                    await minio_client.upload_file(thumb_data, thumb_object_name, 'image/jpeg')
                    thumbnail_url = thumb_object_name
                    # по умолчанию видео не кружок, клиент установит is_circular в метаданных сообщения
                elif content_type.startswith('audio/'):
                    # упрощённый waveform: 100 случайных амплитуд (для MVP)
                    # в реальном проекте вычислить через ffmpeg showwaves
                    import random
                    amplitudes = [random.randint(20, 100) for _ in range(100)]
                    waveform = base64.b64encode(json.dumps(amplitudes).encode()).decode()
            finally:
                os.unlink(tmp_path)

        # Сохраняем в БД
        async with AsyncSessionLocal() as session:
            attachment = Attachment(
                attachment_id=attachment_id,
                message_id=None,
                message_created_at=datetime.now(timezone.utc),
                file_name=metadata.file_name,
                file_size=total_size,
                mime_type=content_type,
                storage_path=object_name,
                uploaded_at=datetime.now(timezone.utc),
                duration=duration,
                waveform=waveform,
                thumbnail_url=thumbnail_url,
                is_circular=is_circular
            )
            session.add(attachment)
            await session.commit()
            await session.refresh(attachment)

        return mess_pb2.UploadAttachmentResponse(
            attachment_id=str(attachment.attachment_id),
            storage_path=object_name
        )

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