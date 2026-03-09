from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Настройки приложения."""
    DEBUG: bool = True
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsAuthGrpc(BaseSettings):
    # gRPC endpoints
    USER_GRPC_SERVER: str = "localhost:50051"
    AUTH_GRPC_SERVER: str = "localhost:50052"
    CHAT_GRPC_SERVER: str = "localhost:50053"

    # Auth/JWT settings
    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "messenger-backend"
    JWT_AUDIENCE: str = "messenger-clients"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settingsA = SettingsAuthGrpc()