from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

# Заглушки: реализуйте логику или подключите существующий crud


async def get_user_chats(db: AsyncSession, user_id: UUID, offset: int, limit: int):
    raise NotImplementedError("Реализуйте get_user_chats в app.grpc_api_Rest.crud.chats")


async def create_chat(db: AsyncSession, data, creator_id: UUID):
    raise NotImplementedError("Реализуйте create_chat в app.grpc_api_Rest.crud.chats")


async def get_chat_by_id(db: AsyncSession, chat_id: UUID):
    raise NotImplementedError("Реализуйте get_chat_by_id в app.grpc_api_Rest.crud.chats")


async def update_chat(db: AsyncSession, chat_id: UUID, data):
    raise NotImplementedError("Реализуйте update_chat в app.grpc_api_Rest.crud.chats")


async def delete_chat(db: AsyncSession, chat_id: UUID):
    raise NotImplementedError("Реализуйте delete_chat в app.grpc_api_Rest.crud.chats")
