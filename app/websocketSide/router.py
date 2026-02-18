import json
from typing import Annotated
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
import logging

from app.websocketSide.config import settings

from app.websocketSide.manager import manager
from app.websocketSide.redis_c import MessageIn, MessageOut, MessageResponse, RedisClient, get_redis_client

from datetime import datetime




logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws")

RedisClientDep = Annotated[RedisClient, Depends(get_redis_client)]

@router.websocket("/chat/{user_id}")
async def websocket_chat_endpoint(websocket: WebSocket, user_id: str):
    """
    WebSocket-эндпоинт для чата.
    - Публичное сообщение: просто текст -> рассылается всем, кроме отправителя.
    - Личное сообщение: @username: текст -> отправляется только username.
    """
    # Проверка origin только в production (DEBUG=False)
    if not settings.DEBUG:
        origin = websocket.headers.get("origin")
        if origin not in settings.ALLOWED_ORIGINS:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    # Подключение
    redis_client: RedisClient = websocket.app.state.redis_client
    await manager.connect(websocket, user_id)
    
    # await redis_client.set_key_with_ttl(key=f"await_offline_message_from{user_id}", key = f"message:{},
    #                                                                                         from {user_id}")

    if not (await redis_client.existOfflineMess(user_id)):
        await redis_client.createOfflineMess(user_id)

    await redis_client.add_online_user_count()
    await redis_client.add_online_user(user_id)
    lastMess = await redis_client.deleteOfflineMess(user_id)
    await manager.send_offline_messages(lastMess,user_id)
    try:
        while True:
            data = await websocket.receive_text()

            if data.startswith("@"):
                # Личное сообщение
                parts = data.split(":", 1)
                if len(parts) == 2:
                    recipient = parts[0][1:].strip()
                    message = parts[1].strip()
                    print(f"ОТ {user_id} Для {recipient} и он {await redis_client.userIsOnline(recipient)}")
                    if await redis_client.userIsOnline(recipient):
                        
                        if recipient:
                            await manager.send_personal_message(
                                f"[От {user_id}]: {message}",
                                recipient
                            )
                    else:
                        mess = MessageOut(
    message_id=123,  # сгенерированный ID
            chat_id="11111111-1111-1111-1111-111111111111",
            sender_id=user_id,
            content=message,
            type="text",
            created_at=datetime.utcnow(),
    )

                        json_s = json.dumps(mess.__dict__, ensure_ascii=False, default= str)
                        a = await redis_client.saveOfflineMess(json_s, user_id, recipient)
                        print(a)

                        # сохранение в редис и бд да и впринципе сохраняить в постгрегсс
                    
            else:
                # Публичное сообщение
                await manager.broadcast(f"{user_id}: {data}", exclude_user=user_id)

    except WebSocketDisconnect:
        logger.info(f"User {user_id} disconnected")
        await redis_client.del_online_user_count()
        await redis_client.del_online_user(user_id)
        await manager.disconnect(user_id)
        await manager.broadcast(f"Пользователь {user_id} покинул чат")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        await redis_client.del_online_user_count()
        await redis_client.del_online_user(user_id)
        await websocket.close()