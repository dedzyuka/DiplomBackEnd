from fastapi import Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import UUID, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator
import uuid

from FastApiClient.database import AsyncSessionLocal
from FastApiClient.core.session_auth import verify_access_session
from FastApiClient.models import User
from FastApiClient.enums import AccountStatus


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.user_id == user_id))
    return result.scalars().first()

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    principal = await verify_access_session(token)
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked authentication session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_user_by_id(db, uuid.UUID(principal.user_id))
    user.access_token = token
    if not user or user.status != AccountStatus.active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


class PaginationParams:
    def __init__(
        self,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        self.limit = limit
        self.offset = offset