from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

from app.FastApiClient.dependencies import get_db, get_current_user, PaginationParams
from app.FastApiClient.schemas import ChatCreate, ChatUpdate, ChatOut, ChatMemberOut, ChatMemberUpdate
from app.FastApiClient.models import User, Chat, ChatMember
from app.FastApiClient.crud import chats as crud
from app.FastApiClient.crud import chat_members as member_crud

router = APIRouter(prefix="/chats", tags=["Chats"])

@router.get("/", response_model=List[ChatOut])
async def get_my_chats(
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    chats = await crud.get_user_chats(db, current_user.user_id, pagination.offset, pagination.limit)
    return chats

@router.post("/", response_model=ChatOut, status_code=201)
async def create_chat(
    data: ChatCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Создаём чат (группу или диалог)
    chat = await crud.create_chat(db, data, creator_id=current_user.user_id)
    return chat

@router.get("/{chat_id}", response_model=ChatOut)
async def get_chat(
    chat_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    chat = await crud.get_chat_by_id(db, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    # Проверка членства
    if not await member_crud.is_member(db, chat_id, current_user.user_id):
        raise HTTPException(status_code=403, detail="Not a member of this chat")
    return chat

@router.put("/{chat_id}", response_model=ChatOut)
async def update_chat(
    chat_id: UUID,
    data: ChatUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Проверка прав (создатель или админ)
    member = await member_crud.get_member(db, chat_id, current_user.user_id)
    if not member or (member.role not in ["owner", "admin"]):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    chat = await crud.update_chat(db, chat_id, data)
    return chat

@router.delete("/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Только создатель (или админ) может удалить чат
    member = await member_crud.get_member(db, chat_id, current_user.user_id)
    if not member or member.role != "owner":
        raise HTTPException(status_code=403, detail="Only owner can delete chat")
    await crud.delete_chat(db, chat_id)
    return None

# Участники
@router.get("/{chat_id}/members", response_model=List[ChatMemberOut])
async def get_chat_members(
    chat_id: UUID,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Проверка членства
    if not await member_crud.is_member(db, chat_id, current_user.user_id):
        raise HTTPException(status_code=403, detail="Not a member")
    members = await member_crud.get_chat_members(db, chat_id, pagination.offset, pagination.limit)
    return members

@router.post("/{chat_id}/members", status_code=201)
async def add_member(
    chat_id: UUID,
    user_id: UUID,  # или список в теле
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Проверка прав (админ/владелец)
    member = await member_crud.get_member(db, chat_id, current_user.user_id)
    if not member or member.role not in ["owner", "admin"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    await member_crud.add_member(db, chat_id, user_id)
    return {"status": "ok"}

@router.delete("/{chat_id}/members/{user_id}", status_code=204)
async def remove_member(
    chat_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Проверка прав (владелец/админ или сам пользователь)
    member = await member_crud.get_member(db, chat_id, current_user.user_id)
    if not member:
        raise HTTPException(status_code=403, detail="Not a member")
    if member.role not in ["owner", "admin"] and current_user.user_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot remove other users")
    await member_crud.remove_member(db, chat_id, user_id)
    return None

@router.patch("/{chat_id}/members/{user_id}", response_model=ChatMemberOut)
async def update_member_role(
    chat_id: UUID,
    user_id: UUID,
    data: ChatMemberUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Только владелец может назначать админов
    owner = await member_crud.get_member(db, chat_id, current_user.user_id)
    if not owner or owner.role != "owner":
        raise HTTPException(status_code=403, detail="Only owner can change roles")
    updated = await member_crud.update_member_role(db, chat_id, user_id, data.role)
    return updated