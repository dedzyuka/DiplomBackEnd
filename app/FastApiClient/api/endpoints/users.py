from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.FastApiClient.dependencies import get_db, get_current_user, PaginationParams
from app.FastApiClient.enums import AccountStatus
from app.FastApiClient.schemas import UserResponse, UserUpdate
from app.FastApiClient.models import Users as User
from app.FastApiClient.crud import users as crud

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/me", response_model=UserResponse)
async def read_current_user(
    current_user: User = Depends(get_current_user)
):
    return current_user

@router.put("/me", response_model=UserResponse)
async def update_current_user(
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    updated = await crud.update_user(db, current_user.user_id, data)
    return updated

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)  # требуется аутентификация
):
    # Публичная информация (можно скрыть приватные поля в схеме)
    user = await crud.get_user_by_id(db, user_id)
    if not user or user.status == AccountStatus.deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.get("/", response_model=list[UserResponse])
async def search_users(
    q: str = "",
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Поиск по нику, email, телефону (с ограничениями)
    users = await crud.search_users(db, q, pagination.offset, pagination.limit)
    return users

@router.delete("/me", status_code=204)
async def delete_current_user(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    await crud.soft_delete_user(db, current_user.user_id)
    # При необходимости инвалидировать сессии в Redis — подключите redis_client
    return None