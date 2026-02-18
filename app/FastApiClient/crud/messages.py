from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

# Заглушки: реализуйте логику работы с БД или подключите существующий crud
# from app.grpc_api_Rest.models import Message


async def get_chat_messages(db: AsyncSession, chat_id: UUID, offset: int, limit: int):
    raise NotImplementedError("Реализуйте get_chat_messages в app.grpc_api_Rest.crud.messages")


async def create_message(db: AsyncSession, chat_id: UUID, sender_id: UUID, data):
    raise NotImplementedError("Реализуйте create_message в app.grpc_api_Rest.crud.messages")


async def get_message(db: AsyncSession, message_id: int):
    raise NotImplementedError("Реализуйте get_message в app.grpc_api_Rest.crud.messages")


async def update_message(db: AsyncSession, message_id: int, data):
    raise NotImplementedError("Реализуйте update_message в app.grpc_api_Rest.crud.messages")


async def soft_delete_message(db: AsyncSession, message_id: int):
    raise NotImplementedError("Реализуйте soft_delete_message в app.grpc_api_Rest.crud.messages")
