from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

# Строка подключения к PostgreSQL (асинхронный драйвер asyncpg)
DATABASE_URL = DATABASE_URL = "postgresql+asyncpg://bodya11@localhost:5432/messenger_db_dip"

# Движок SQLAlchemy
engine = create_async_engine(DATABASE_URL, echo=True)

# Фабрика сессий
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Базовый класс для всех моделей
Base = declarative_base()
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)