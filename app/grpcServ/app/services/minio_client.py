import io
from minio import Minio
from minio.error import S3Error
from core.config import settings

class MinioClient:
    def __init__(self):
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self.bucket = settings.MINIO_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self):
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    async def upload_file(self, file_data: bytes, object_name: str, content_type: str) -> str:
        """Загружает файл и возвращает путь (object_name)."""
        file_size = len(file_data)
        data_stream = io.BytesIO(file_data)
        self.client.put_object(
            self.bucket,
            object_name,
            data_stream,
            file_size,
            content_type=content_type,
        )
        return object_name

    async def get_presigned_url(self, object_name: str, expires: int = 3600) -> str:
        """Возвращает временную ссылку на файл."""
        return self.client.presigned_get_object(self.bucket, object_name, expires=expires)

    async def delete_file(self, object_name: str):
        self.client.remove_object(self.bucket, object_name)

# Добавить в config.py настройки MinIO