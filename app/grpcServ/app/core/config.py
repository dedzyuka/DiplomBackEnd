from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "messenger-backend"
    JWT_AUDIENCE: str = "messenger-clients"
    REDIS_EVENTS_CHANNEL: str = "messenger:events"

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False
    MINIO_BUCKET: str = "messenger"

    # Добавленные поля для видеозвонков:
    LIVEKIT_URL: str = "http://localhost:7880"
    LIVEKIT_WS_URL: str = "ws://192.168.100.247:7880" 
    LIVEKIT_API_KEY: str = "api-key"
    LIVEKIT_API_SECRET: str = "mysecretkey123456789012345678901234"
    CALL_GRPC_SERVER: str = "localhost:50057"   # если используется

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()