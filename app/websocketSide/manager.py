from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import DefaultDict, Iterable

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class ConnectionRef:
    user_id: str
    websocket: WebSocket


class ConnectionManager:
    def __init__(self):
        self._connections: DefaultDict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, websocket: WebSocket, user_id: str) -> ConnectionRef:
        await websocket.accept()
        self._connections[user_id].add(websocket)
        logger.info("WS connected user_id=%s online_users=%s", user_id, len(self._connections))
        return ConnectionRef(user_id=user_id, websocket=websocket)

    async def disconnect(self, connection: ConnectionRef) -> None:
        user_connections = self._connections.get(connection.user_id)
        if not user_connections:
            return

        user_connections.discard(connection.websocket)
        if not user_connections:
            self._connections.pop(connection.user_id, None)

        logger.info("WS disconnected user_id=%s online_users=%s", connection.user_id, len(self._connections))

    async def send_to_user(self, user_id: str, payload: dict) -> bool:
        targets = self._connections.get(user_id)
        if not targets:
            return False
        dead = []
        # ❗️ Итерируемся по копии множества
        for ws in list(targets):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            targets.discard(ws)
        if not targets:
            self._connections.pop(user_id, None)
        return bool(targets)

        return bool(targets)

    async def send_to_users(self, user_ids: Iterable[str], payload: dict, exclude_user_id: str | None = None) -> None:
        for user_id in user_ids:
            if exclude_user_id and user_id == exclude_user_id:
                continue
            await self.send_to_user(user_id, payload)

    @property
    def online_users_count(self) -> int:
        return len(self._connections)

    def get_online_users(self) -> list[str]:
        return list(self._connections.keys())


manager = ConnectionManager()