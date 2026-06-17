from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base


# Строка подключения к PostgreSQL (асинхронный драйвер asyncpg)
DATABASE_URL = "postgresql+asyncpg://bodya11:bodya11@postgres:5432/messengerdbdip"

# Движок SQLAlchemy
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# Базовый класс для всех моделей
Base = declarative_base()