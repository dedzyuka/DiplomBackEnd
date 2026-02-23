from pydantic_settings import BaseSettings


# class Settings(BaseSettings):
#     SECRET_KEY: str = "change-me-in-production"
#     ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
#     REFRESH_TOKEN_EXPIRE_DAYS: int = 7

#     class Config:
#         env_file = ".env"
#         case_sensitive = False


# settings = Settings()

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    USER_GRPC_SERVER: str = "localhost:50051"
    AUTH_GRPC_SERVER: str = "localhost:50052"

    class Config:
        env_file = ".env"

settings = Settings()