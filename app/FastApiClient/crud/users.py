from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.FastApiClient.models import User


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.user_id == user_id))
    return result.scalars().first()


async def update_user(db: AsyncSession, user_id: UUID, data) -> User:
    raise NotImplementedError("Реализуйте update_user в app.grpc_api_Rest.crud.users")


async def search_users(db: AsyncSession, q: str, offset: int, limit: int):
    raise NotImplementedError("Реализуйте search_users в app.grpc_api_Rest.crud.users")


async def soft_delete_user(db: AsyncSession, user_id: UUID):
    raise NotImplementedError("Реализуйте soft_delete_user в app.grpc_api_Rest.crud.users")


async def get_user_by_login(db: AsyncSession, login: str) -> User | None:
    """Поиск по email, phone или nick_name."""
    raise NotImplementedError("Реализуйте get_user_by_login в app.grpc_api_Rest.crud.users")


async def create_user(db: AsyncSession, data: dict) -> User:
    raise NotImplementedError("Реализуйте create_user в app.grpc_api_Rest.crud.users")
