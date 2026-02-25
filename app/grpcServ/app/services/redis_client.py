import os
from typing import Optional

from redis.asyncio import Redis


class RedisClient:
    def __init__(self, redis_url: str, key_prefix: str = "messenger"):
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._prefix = key_prefix

    def _key(self, *parts: str) -> str:
        return ":".join((self._prefix, *parts))

    async def ping(self) -> bool:
        return bool(await self._redis.ping())

    async def close(self) -> None:
        await self._redis.aclose()

    async def set_refresh_token(self, user_id: str, refresh_token: str, ttl_seconds: int) -> None:
        await self._redis.set(self._key("auth", "refresh", user_id), refresh_token, ex=max(1, ttl_seconds))

    async def get_refresh_token(self, user_id: str) -> Optional[str]:
        return await self._redis.get(self._key("auth", "refresh", user_id))

    async def delete_refresh_token(self, user_id: str) -> None:
        await self._redis.delete(self._key("auth", "refresh", user_id))


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_PREFIX = os.getenv("REDIS_PREFIX", "messenger")

redis_client = RedisClient(redis_url=REDIS_URL, key_prefix=REDIS_PREFIX)