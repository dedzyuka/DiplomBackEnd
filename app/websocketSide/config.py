from pydantic_settings import BaseSettings
from typing import List



from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # gRPC endpoints
    """Настройки приложения."""
    DEBUG: bool = True
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]


    USER_GRPC_SERVER: str = "localhost:50051"
    AUTH_GRPC_SERVER: str = "localhost:50052"
    CHAT_GRPC_SERVER: str = "localhost:50053"
    CALL_GRPC_SERVER: str = "localhost:50057"

    # Auth/JWT settings
    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "messenger-backend"
    JWT_AUDIENCE: str = "messenger-clients"
    

    # Redis session store
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PREFIX: str = "messenger"
    REDIS_EVENTS_CHANNEL: str = "messenger:events"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()