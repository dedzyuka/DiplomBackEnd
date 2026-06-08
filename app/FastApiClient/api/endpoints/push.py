from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, timezone

from FastApiClient.dependencies import get_db, get_current_user
from FastApiClient.models import User, DeviceToken

router = APIRouter(prefix="/push", tags=["Push"])

class RegisterTokenRequest(BaseModel):
    device_token: str
    device_type: str  # "ios" или "android"

@router.post("/register", status_code=200)
async def register_push_token(
    data: RegisterTokenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Проверить, нет ли уже такого токена
    from sqlalchemy import select
    stmt = select(DeviceToken).where(DeviceToken.device_token == data.device_token)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        # Обновить user_id на случай смены владельца
        existing.user_id = current_user.user_id
        existing.updated_at = datetime.now(timezone.utc)
    else:
        token = DeviceToken(
            user_id=current_user.user_id,
            device_type=data.device_type,
            device_token=data.device_token
        )
        db.add(token)
    await db.commit()
    return {"status": "ok"}

@router.delete("/unregister", status_code=204)
async def unregister_push_token(
    data: RegisterTokenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from sqlalchemy import delete
    stmt = delete(DeviceToken).where(DeviceToken.device_token == data.device_token)
    await db.execute(stmt)
    await db.commit()
    return None