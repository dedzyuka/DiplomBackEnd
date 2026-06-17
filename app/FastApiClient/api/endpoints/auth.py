from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
import uuid

from app.FastApiClient.dependencies import get_db, get_current_user
from app.FastApiClient.core.security import (
    create_access_token, create_refresh_token,
    verify_token, verify_password
)
from app.FastApiClient.schemas import LoginRequest, RegisterRequest, Token, RefreshRequest, SessionInfo
from app.FastApiClient.models import Users as User, SessionEvents as SessionEvent
from app.FastApiClient.crud.users import get_user_by_id, get_user_by_login, create_user
from app.FastApiClient.enums import AccountStatus

try:
    from app.FastApiClient.core.redis_client import redis_client
except ImportError:
    redis_client = None

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=Token, status_code=201)
async def register(
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    # Проверка уникальности
    existing = await get_user_by_login(db, data.login)
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")
    
    # Создание пользователя
    user = await create_user(db, data.model_dump())
    
    # Генерация токенов
    access_token = create_access_token({"sub": str(user.user_id)})
    refresh_token = create_refresh_token({"sub": str(user.user_id)})
    
    if redis_client:
        await redis_client.set_refresh_token(str(user.user_id), refresh_token)
    
    session_event = SessionEvent(
        user_id=user.user_id,
        action="register",
        ip_address=None,
        user_agent=None
    )
    db.add(session_event)
    await db.commit()
    
    return Token(access_token=access_token, refresh_token=refresh_token)

@router.post("/login", response_model=Token)
async def login(
    data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    user = await get_user_by_login(db, data.login)
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if user.status != AccountStatus.active:
        raise HTTPException(status_code=403, detail="Account is not active")
    
    access_token = create_access_token({"sub": str(user.user_id)})
    refresh_token = create_refresh_token({"sub": str(user.user_id)})
    
    if redis_client:
        await redis_client.set_refresh_token(str(user.user_id), refresh_token)
    
    session_event = SessionEvent(
        user_id=user.user_id,
        action="login",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )
    db.add(session_event)
    await db.commit()
    
    return Token(access_token=access_token, refresh_token=refresh_token)

@router.post("/refresh", response_model=Token)
async def refresh_token(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db)
):
    payload = verify_token(data.refresh_token, "refresh")
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    if redis_client:
        stored = await redis_client.get_refresh_token(user_id)
        if stored != data.refresh_token:
            raise HTTPException(status_code=401, detail="Token revoked")
    
    user = await get_user_by_id(db, uuid.UUID(user_id))
    if not user or user.status != AccountStatus.active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    
    # Генерируем новую пару
    new_access = create_access_token({"sub": user_id})
    new_refresh = create_refresh_token({"sub": user_id})
    
    if redis_client:
        await redis_client.set_refresh_token(user_id, new_refresh)
    
    return Token(access_token=new_access, refresh_token=new_refresh)

@router.post("/logout", status_code=204)
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if redis_client:
        await redis_client.delete_refresh_token(str(current_user.user_id))
    
    session_event = SessionEvent(
        user_id=current_user.user_id,
        action="logout",
        ip_address=None,
        user_agent=None
    )
    db.add(session_event)
    await db.commit()
    return None

@router.get("/sessions", response_model=list[SessionInfo])
async def get_sessions(
    current_user: User = Depends(get_current_user)
):
    if not redis_client:
        return []
    sessions = await redis_client.get_user_sessions(str(current_user.user_id))
    return sessions