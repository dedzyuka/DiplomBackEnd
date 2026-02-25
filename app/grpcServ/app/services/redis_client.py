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

    async def set_session_tokens(
        self,
        *,
        session_id: str,
        user_id: str,
        refresh_token: str,
        access_token: str,
        ttl_seconds: int,
    ) -> None:
        session_key = self._key("auth", "session", session_id)
        await self._redis.hset(
            session_key,
            mapping={
                "user_id": user_id,
                "refresh_token": refresh_token,
                "access_token": access_token,
            },
        )
        await self._redis.expire(session_key, max(1, ttl_seconds))
        await self._redis.sadd(self._key("auth", "user_sessions", user_id), session_id)

    async def get_session_tokens(self, session_id: str) -> Optional[dict[str, str]]:
        session_key = self._key("auth", "session", session_id)
        data = await self._redis.hgetall(session_key)
        return data or None

    async def delete_session(self, session_id: str) -> None:
        session_key = self._key("auth", "session", session_id)
        user_id = await self._redis.hget(session_key, "user_id")
        await self._redis.delete(session_key)
        if user_id:
            await self._redis.srem(self._key("auth", "user_sessions", user_id), session_id)


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_PREFIX = os.getenv("REDIS_PREFIX", "messenger")

redis_client = RedisClient(redis_url=REDIS_URL, key_prefix=REDIS_PREFIX)