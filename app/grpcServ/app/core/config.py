from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "messenger-backend"
    JWT_AUDIENCE: str = "messenger-clients"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()