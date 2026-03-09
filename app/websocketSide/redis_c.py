from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

import redis.asyncio as redis


@dataclass
class OfflineMessage:
    sender_id: str
    recipient_id: str
    payload: dict

    def to_json(self) -> str:
        return json.dumps(
            {
                "sender_id": self.sender_id,
                "recipient_id": self.recipient_id,
                "payload": self.payload,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str) -> "OfflineMessage":
        data = json.loads(raw)
        return cls(
            sender_id=data["sender_id"],
            recipient_id=data["recipient_id"],
            payload=data["payload"],
        )


class RedisClient:
    def __init__(self, url: str = "redis://localhost:6379/0"):
        self.url = url
        self.client: Optional[redis.Redis] = None

    async def create(self) -> None:
        pool = redis.ConnectionPool.from_url(
            self.url,
            decode_responses=True,
            max_connections=50,
        )
        self.client = redis.Redis(connection_pool=pool)

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()

    def _require_client(self) -> redis.Redis:
        if self.client is None:
            raise RuntimeError("RedisClient is not initialized")
        return self.client

    @staticmethod
    def _online_users_key() -> str:
        return "ws:online_users"

    @staticmethod
    def _offline_queue_key(user_id: str) -> str:
        return f"ws:offline:{user_id}"

    async def add_online_user(self, user_id: str) -> None:
        await self._require_client().sadd(self._online_users_key(), user_id)

    async def remove_online_user(self, user_id: str) -> None:
        await self._require_client().srem(self._online_users_key(), user_id)

    async def is_user_online(self, user_id: str) -> bool:
        return bool(await self._require_client().sismember(self._online_users_key(), user_id))

    async def enqueue_offline_message(self, message: OfflineMessage) -> None:
        await self._require_client().rpush(
            self._offline_queue_key(message.recipient_id),
            message.to_json(),
        )

    async def dequeue_all_offline_messages(self, user_id: str) -> list[OfflineMessage]:
        redis_client = self._require_client()
        key = self._offline_queue_key(user_id)
        raw_messages = await redis_client.lrange(key, 0, -1)
        if raw_messages:
            await redis_client.delete(key)
        return [OfflineMessage.from_json(raw) for raw in raw_messages]