from sqlalchemy.ext.asyncio import AsyncSession

# Заглушки


async def get_for_message(db: AsyncSession, message_id: int):
    raise NotImplementedError("Реализуйте get_for_message в app.grpc_api_Rest.crud.reactions")


async def add_reaction(db: AsyncSession, message_id: int, user_id, emoji: str):
    raise NotImplementedError("Реализуйте add_reaction в app.grpc_api_Rest.crud.reactions")


async def remove_reaction(db: AsyncSession, message_id: int, user_id, emoji: str):
    raise NotImplementedError("Реализуйте remove_reaction в app.grpc_api_Rest.crud.reactions")
