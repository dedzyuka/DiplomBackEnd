from fastapi import Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, AsyncGenerator
import uuid

from app.FastApiClient.database import AsyncSessionLocal
from app.FastApiClient.core.security import verify_token
from app.FastApiClient.models import User
from app.FastApiClient.schemas import UserResponse
from app.FastApiClient.enums import AccountStatus
from app.FastApiClient.crud.users import get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    payload = verify_token(token, "access")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = await get_user_by_id(db, uuid.UUID(user_id))
    if not user or user.status != AccountStatus.active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user

# Пагинация
class PaginationParams:
    def __init__(
        self,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0)
    ):
        self.limit = limit
        self.offset = offset