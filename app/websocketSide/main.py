from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import grpc
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from protobuf import mess_pb2_grpc
from redis_c import RedisClient
from router import handle_redis_event, router as websocket_router
from websocketSide.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting WebSocket service")

    redis_client = RedisClient(settings.REDIS_URL)
    await redis_client.create()
    app.state.redisclient = redis_client

    message_channel = grpc.insecure_channel(settings.MESSAGE_GRPC_SERVER)
    message_stub = mess_pb2_grpc.MessageServiceStub(message_channel)

    call_channel = grpc.insecure_channel(settings.CALL_GRPC_SERVER)
    call_stub = mess_pb2_grpc.CallServiceStub(call_channel)

    app.state.messagestub = message_stub
    app.state.callstub = call_stub

    if redis_client is None or redis_client.client is None:
        logger.error("Redis client not initialized")
        raise RuntimeError("Redis client not initialized")

    pubsub = redis_client.client.pubsub()
    await pubsub.subscribe(settings.REDIS_EVENTS_CHANNEL)
    app.state.redispubsub = pubsub

    async def event_listener():
        try:
            while True:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )
                    if message and message.get("type") == "message":
                        logger.info("Redis event received: %s", message["data"])
                        await handle_redis_event(app, message["data"])
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Pubsub polling error: %s", str(e), exc_info=True)
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Event listener task cancelled")

    listener_task = asyncio.create_task(event_listener())

    try:
        yield
    finally:
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass
        await pubsub.close()
        message_channel.close()
        call_channel.close()
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
    allow_credentials=True,
    allow_methods=["*"],
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
        "server_time": datetime.utcnow().isoformat(),
    }