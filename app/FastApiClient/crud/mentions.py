from sqlalchemy.ext.asyncio import AsyncSession

# Заглушки


async def get_for_message(db: AsyncSession, message_id: int):
    raise NotImplementedError("Реализуйте get_for_message в app.grpc_api_Rest.crud.mentions")
