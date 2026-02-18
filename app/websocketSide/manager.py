import json
import logging
from typing import Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Управляет WebSocket-соединениями и офлайн-очередью."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.offline_messages: Dict[str, List[str]] = {}

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        """Принимает соединение и добавляет пользователя в онлайн."""
        await websocket.accept()
        self.active_connections[user_id] = websocket
        await self._send_offline_messages(user_id)
        logger.info(f"User {user_id} connected. Online: {len(self.active_connections)}")

    async def disconnect(self, user_id: str) -> None:
        """Удаляет пользователя из активных соединений."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info(f"User {user_id} disconnected. Online: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, user_id: str) -> None:
        """Отправляет личное сообщение. Если получатель офлайн – сохраняет в очередь."""
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)
        else:
            self.offline_messages.setdefault(user_id, []).append(message)
            logger.debug(f"Offline message stored for {user_id}")

    async def broadcast(self, message: str, exclude_user: Optional[str] = None) -> None:
        """Отправляет сообщение всем онлайн-пользователям, кроме указанного."""
        for uid, conn in self.active_connections.items():
            if exclude_user and uid == exclude_user:
                continue
            await conn.send_text(message)

    async def _send_offline_messages(self, user_id: str) -> None:
        """Отправляет накопленные офлайн-сообщения при подключении."""
        if user_id in self.offline_messages:
            for msg in self.offline_messages[user_id]:
                await self.send_personal_message(msg, user_id)
            del self.offline_messages[user_id]
    async def send_offline_messages(self, lastMess:str, user_id:str):
        last_mess_json = {"LastMess":lastMess}
        json_string = json.dumps(last_mess_json, ensure_ascii=False)
        await self.send_personal_message(json_string, user_id)

    def is_online(self, user_id: str) -> bool:
        """Проверяет, находится ли пользователь в сети."""
        return user_id in self.active_connections

    def get_online_users(self) -> List[str]:
        """Возвращает список идентификаторов онлайн-пользователей."""
        return list(self.active_connections.keys())


# Глобальный экземпляр (синглтон)
manager = ConnectionManager()