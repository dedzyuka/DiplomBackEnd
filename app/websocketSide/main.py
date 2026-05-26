# app/websocketSide/main.py

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import logging

from fastapi import FastAPI, logger
from fastapi.middleware.cors import CORSMiddleware
import grpc  # обычный синхронный grpc

from config import settings
from redis_c import RedisClient
from router import handle_redis_event, router as websocket_router
from manager import manager
from protobuf import mess_pb2_grpc

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting WebSocket service")

    # Redis клиент
    redis_client = RedisClient()
    await redis_client.create()
    app.state.redis_client = redis_client

    # gRPC канал для MessageService
    channel = grpc.insecure_channel(settings.CHAT_GRPC_SERVER)
    message_stub = mess_pb2_grpc.MessageServiceStub(channel)
    app.state.message_stub = message_stub

    # Подписка на события Redis
    pubsub = redis_client.client.pubsub()          # <- Убрали await
    await pubsub.subscribe(settings.REDIS_EVENTS_CHANNEL)  # <- await здесь
    app.state.redis_pubsub = pubsub

    async def event_listener():
        async for message in pubsub.listen():
            if message["type"] == "message":
                await handle_redis_event(app, message["data"])

    asyncio.create_task(event_listener())

    yield

    # Cleanup
    channel.close()
    await redis_client.close()
    logger.info("WebSocket service stopped")



app = FastAPI(
    title="Messenger WebSocket Service",
    description="Realtime transport for messenger delivery",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_headers=["*"],
)

app.include_router(websocket_router)



@app.get("/")
async def root():
    return {
        "service": "websocket",
        "status": "running",
        "ws_endpoint": "ws://localhost:8000/ws/chat",
    }

@app.get("/ws-info")
async def websocket_info():
    return {
        "online_users_count": manager.online_users_count,
        "online_users": manager.get_online_users(),
        "server_time": datetime.utcnow().isoformat(),
    }