from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

# Заглушки: реализуйте логику работы с контактами


async def get_contacts(db: AsyncSession, user_id: UUID, offset: int, limit: int):
    raise NotImplementedError("Реализуйте get_contacts в app.grpc_api_Rest.crud.contacts")


async def get_pending_requests(db: AsyncSession, user_id: UUID, offset: int, limit: int):
    raise NotImplementedError("Реализуйте get_pending_requests в app.grpc_api_Rest.crud.contacts")


async def create_contact_request(db: AsyncSession, user_id: UUID, contact_user_id: UUID):
    raise NotImplementedError("Реализуйте create_contact_request в app.grpc_api_Rest.crud.contacts")


async def update_contact_status(db: AsyncSession, user_id: UUID, contact_user_id: UUID, status):
    raise NotImplementedError("Реализуйте update_contact_status в app.grpc_api_Rest.crud.contacts")


async def delete_contact(db: AsyncSession, user_id: UUID, contact_user_id: UUID):
    raise NotImplementedError("Реализуйте delete_contact в app.grpc_api_Rest.crud.contacts")
