from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

from app.FastApiClient.dependencies import get_db, get_current_user, PaginationParams
from app.FastApiClient.schemas import MessageCreate, MessageUpdate, MessageOut, MessageWithReactions
from app.FastApiClient.models import User, Message
from app.FastApiClient.crud import messages as crud
from app.FastApiClient.crud import chat_members as member_crud
from app.FastApiClient.crud import reactions as reaction_crud
from app.FastApiClient.crud import mentions as mention_crud
try:
    from app.websocket.manager import ws_manager
except ImportError:
    ws_manager = None  # опционально для WebSocket

router = APIRouter(prefix="/chats/{chat_id}/messages", tags=["Messages"])

@router.get("/", response_model=List[MessageOut])
async def get_messages(
    chat_id: UUID,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Проверка членства
    if not await member_crud.is_member(db, chat_id, current_user.user_id):
        raise HTTPException(status_code=403, detail="Not a member")
    messages = await crud.get_chat_messages(db, chat_id, pagination.offset, pagination.limit)
    return messages

@router.post("/", response_model=MessageOut, status_code=201)
async def create_message(
    chat_id: UUID,
    data: MessageCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Проверка членства и прав (можно ли писать)
    if not await member_crud.can_send_message(db, chat_id, current_user.user_id):
        raise HTTPException(status_code=403, detail="Cannot send message to this chat")
    
    # Создаём сообщение в БД
    message = await crud.create_message(db, chat_id, current_user.user_id, data)
    
    # Отправляем через WebSocket всем участникам чата (фоново)
    if ws_manager:
        background_tasks.add_task(
            ws_manager.broadcast_to_chat,
            chat_id,
            MessageOut.model_validate(message).model_dump()
        )
    
    return message

@router.get("/{message_id}", response_model=MessageWithReactions)
async def get_message(
    chat_id: UUID,
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Проверка членства
    if not await member_crud.is_member(db, chat_id, current_user.user_id):
        raise HTTPException(status_code=403, detail="Not a member")
    
    message = await crud.get_message(db, message_id)
    if not message or message.chat_id != chat_id:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Дополнительно загружаем реакции и упоминания
    reactions = await reaction_crud.get_for_message(db, message_id)
    mentions = await mention_crud.get_for_message(db, message_id)
    
    return MessageWithReactions(
        **message.__dict__,
        reactions=reactions,
        mentions=[m.mentioned_user_id for m in mentions]
    )

@router.put("/{message_id}", response_model=MessageOut)
async def update_message(
    chat_id: UUID,
    message_id: int,
    data: MessageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Проверка, что сообщение принадлежит текущему пользователю
    message = await crud.get_message(db, message_id)
    if not message or message.sender_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Can only edit own messages")
    
    updated = await crud.update_message(db, message_id, data)
    return updated

@router.delete("/{message_id}", status_code=204)
async def delete_message(
    chat_id: UUID,
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    message = await crud.get_message(db, message_id)
    if not message or message.chat_id != chat_id:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Удалить может автор или админ чата
    if message.sender_id == current_user.user_id:
        await crud.soft_delete_message(db, message_id)
    else:
        # Проверка, является ли пользователь админом чата
        member = await member_crud.get_member(db, chat_id, current_user.user_id)
        if not member or member.role not in ["owner", "admin"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        await crud.soft_delete_message(db, message_id)
    
    return None

# Реакции
@router.post("/{message_id}/reactions", status_code=201)
async def add_reaction(
    chat_id: UUID,
    message_id: int,
    emoji: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not await member_crud.is_member(db, chat_id, current_user.user_id):
        raise HTTPException(status_code=403, detail="Not a member")
    
    await reaction_crud.add_reaction(db, message_id, current_user.user_id, emoji)
    return {"status": "ok"}

@router.delete("/{message_id}/reactions", status_code=204)
async def remove_reaction(
    chat_id: UUID,
    message_id: int,
    emoji: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    await reaction_crud.remove_reaction(db, message_id, current_user.user_id, emoji)
    return None