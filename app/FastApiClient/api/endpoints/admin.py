from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

from app.FastApiClient.dependencies import get_db, get_current_user, PaginationParams
from app.FastApiClient.schemas import UserResponse, AuditLogOut
from app.FastApiClient.models import Users as User
from app.FastApiClient.crud import admin as admin_crud

router = APIRouter(prefix="/admin", tags=["Admin"])

async def verify_admin(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:  # предположим, есть поле is_admin
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user

@router.get("/users", response_model=List[UserResponse])
async def get_all_users(
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    users = await admin_crud.get_all_users(db, pagination.offset, pagination.limit)
    return users

@router.post("/users/{user_id}/block", status_code=200)
async def block_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    await admin_crud.block_user(db, user_id)
    # При необходимости здесь можно инвалидировать сессии пользователя в Redis
    return {"status": "blocked"}

@router.get("/audit-logs", response_model=List[AuditLogOut])
async def get_audit_logs(
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    logs = await admin_crud.get_audit_logs(db, pagination.offset, pagination.limit)
    return logs