from sqlalchemy.ext.asyncio import AsyncSession

# Заглушки


async def get_all_users(db: AsyncSession, offset: int, limit: int):
    raise NotImplementedError("Реализуйте get_all_users в app.grpc_api_Rest.crud.admin")


async def block_user(db: AsyncSession, user_id):
    raise NotImplementedError("Реализуйте block_user в app.grpc_api_Rest.crud.admin")


async def get_audit_logs(db: AsyncSession, offset: int, limit: int):
    raise NotImplementedError("Реализуйте get_audit_logs в app.grpc_api_Rest.crud.admin")
