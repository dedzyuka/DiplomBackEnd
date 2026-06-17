import asyncio
from sqlalchemy import text

from app.database import engine
from app.services.models import Base

async def main():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)

if __name__ == "__main__":
    asyncio.run(main())