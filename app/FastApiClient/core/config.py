from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    USER_GRPC_SERVER: str = "localhost:50051"
    AUTH_GRPC_SERVER: str = "localhost:50052"
    CHAT_GRPC_SERVER: str = "localhost:50053"
    MESSAGE_GRPC_SERVER: str = "localhost:50054"
    CONTACT_GRPC_SERVER: str = "localhost:50055"
    ATTACHMENT_GRPC_SERVER: str = "localhost:50056"
    CALL_GRPC_SERVER: str = "localhost:50057"

    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "messenger-backend"
    JWT_AUDIENCE: str = "messenger-clients"

    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_PREFIX: str = "messenger"

    TRANSLATION_PROVIDER: str = "mymemory"
    TRANSLATION_PROVIDER_URL: str = "https://api.mymemory.translated.net/get"
    TRANSLATION_MAX_TEXT_LENGTH: int = 5000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()