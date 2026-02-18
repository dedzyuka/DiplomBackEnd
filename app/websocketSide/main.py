from contextlib import asynccontextmanager
from datetime import datetime
import logging
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.websocketSide.config import settings
from app.websocketSide.redis_c import RedisClient, get_redis_client
from app.websocketSide.router import router as websocket_router
from app.websocketSide.manager import manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting Anonymous Messenger API...")
    print("📡 WebSocket endpoint: ws://localhost:8000/ws/chat/{user_id}")

    redis_client = RedisClient()
    await redis_client.create()
    app.state.redis_client = redis_client
    await redis_client.set_key_with_ttl(key="online_users_count", value="0", ttl=3000)
    yield
    await redis_client.close()
    # Shutdown
    print("👋 Shutting down...")


app = FastAPI(
    title="Anonymous Messenger API",
    description="Secure anonymous messaging platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS для HTTP-запросов
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем WebSocket роутер
app.include_router(websocket_router)


@app.get("/")
async def root():
    return {
        "message": "Anonymous Messenger API",
        "status": "running",
        "websocket_endpoint": "ws://localhost:8000/ws/chat/{user_id}",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/ws-info")
async def websocket_info():
    """Базовая информация о WebSocket-соединениях."""
    return {
        "online_users": len(manager.active_connections),
    }


@app.get("/ws-info/stats")
async def get_websocket_stats():
    """Детальная статистика."""
    offline_queue_sizes = {
        str(uid): len(msgs) for uid, msgs in manager.offline_messages.items()
    }
    return {
        "online_users": len(manager.active_connections),
        "server_time": datetime.now().isoformat(),
        "offline_messages_queue": offline_queue_sizes,
    }