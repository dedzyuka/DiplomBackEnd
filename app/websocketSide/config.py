from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DEBUG: bool = True

    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8002",
        "http://127.0.0.1:8002",
    ]

    USER_GRPC_SERVER: str = "localhost:50051"
    AUTH_GRPC_SERVER: str = "localhost:50052"
    CHAT_GRPC_SERVER: str = "localhost:50053"
    MESSAGE_GRPC_SERVER: str = "localhost:50054"
    CALL_GRPC_SERVER: str = "localhost:50057"

    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "messenger-backend"
    JWT_AUDIENCE: str = "messenger-clients"

    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_PREFIX: str = "messenger"
    REDIS_EVENTS_CHANNEL: str = "messengerevents"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()