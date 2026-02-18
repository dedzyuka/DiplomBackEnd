from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

# Заглушки: реализуйте логику или подключите существующий crud


async def is_member(db: AsyncSession, chat_id: UUID, user_id: UUID) -> bool:
    raise NotImplementedError("Реализуйте is_member в app.grpc_api_Rest.crud.chat_members")


async def can_send_message(db: AsyncSession, chat_id: UUID, user_id: UUID) -> bool:
    raise NotImplementedError("Реализуйте can_send_message в app.grpc_api_Rest.crud.chat_members")


async def get_member(db: AsyncSession, chat_id: UUID, user_id: UUID):
    raise NotImplementedError("Реализуйте get_member в app.grpc_api_Rest.crud.chat_members")


async def get_chat_members(db: AsyncSession, chat_id: UUID, offset: int, limit: int):
    raise NotImplementedError("Реализуйте get_chat_members в app.grpc_api_Rest.crud.chat_members")


async def add_member(db: AsyncSession, chat_id: UUID, user_id: UUID):
    raise NotImplementedError("Реализуйте add_member в app.grpc_api_Rest.crud.chat_members")


async def remove_member(db: AsyncSession, chat_id: UUID, user_id: UUID):
    raise NotImplementedError("Реализуйте remove_member в app.grpc_api_Rest.crud.chat_members")


async def update_member_role(db: AsyncSession, chat_id: UUID, user_id: UUID, role):
    raise NotImplementedError("Реализуйте update_member_role в app.grpc_api_Rest.crud.chat_members")
