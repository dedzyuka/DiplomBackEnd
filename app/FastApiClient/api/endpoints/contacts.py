from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

from app.FastApiClient.dependencies import get_db, get_current_user, PaginationParams
from app.FastApiClient.schemas import ContactOut, ContactCreate, ContactUpdateStatus
from app.FastApiClient.models import User
from app.FastApiClient.crud import contacts as crud

router = APIRouter(prefix="/contacts", tags=["Contacts"])

@router.get("/", response_model=List[ContactOut])
async def get_contacts(
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    contacts = await crud.get_contacts(db, current_user.user_id, pagination.offset, pagination.limit)
    return contacts

@router.get("/requests", response_model=List[ContactOut])
async def get_incoming_requests(
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    requests = await crud.get_pending_requests(db, current_user.user_id, pagination.offset, pagination.limit)
    return requests

@router.post("/", response_model=ContactOut, status_code=201)
async def add_contact(
    data: ContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Проверка, что не пытается добавить самого себя
    if data.contact_user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Cannot add yourself")
    
    contact = await crud.create_contact_request(db, current_user.user_id, data.contact_user_id)
    return contact

@router.patch("/{contact_user_id}", response_model=ContactOut)
async def update_contact_status(
    contact_user_id: UUID,
    data: ContactUpdateStatus,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Обновление статуса (принять/отклонить) — только для входящих запросов
    updated = await crud.update_contact_status(db, current_user.user_id, contact_user_id, data.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Contact request not found")
    return updated

@router.delete("/{contact_user_id}", status_code=204)
async def delete_contact(
    contact_user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Удаление из контактов (или отклонение запроса)
    await crud.delete_contact(db, current_user.user_id, contact_user_id)
    return None