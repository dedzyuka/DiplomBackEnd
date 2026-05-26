import json
import os
from datetime import datetime, timezone
from typing import Optional

from redis.asyncio import Redis


class RedisClient:
    def __init__(self, redis_url: str, key_prefix: str = "messenger"):
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._prefix = key_prefix

    def _key(self, *parts: str) -> str:
        return ":".join((self._prefix, *parts))

    def _session_key(self, session_id: str) -> str:
        return self._key("auth", "session", session_id)

    def _user_sessions_key(self, user_id: str) -> str:
        return self._key("auth", "user_sessions", user_id)

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
        device_info: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        created_at: datetime | None = None,
        last_seen_at: datetime | None = None,
    ) -> None:
        session_key = self._session_key(session_id)

        now = datetime.now(timezone.utc)
        created_at = created_at or now
        last_seen_at = last_seen_at or now

        await self._redis.hset(
            session_key,
            mapping={
                "user_id": user_id,
                "refresh_token": refresh_token,
                "access_token": access_token,
                "device_info": device_info or "",
                "ip_address": ip_address or "",
                "user_agent": user_agent or "",
                "created_at": created_at.isoformat(),
                "last_seen_at": last_seen_at.isoformat(),
            },
        )
        await self._redis.expire(session_key, max(1, ttl_seconds))
        await self._redis.sadd(self._user_sessions_key(user_id), session_id)

    async def get_session_tokens(self, session_id: str) -> Optional[dict[str, str]]:
        session_key = self._session_key(session_id)
        data = await self._redis.hgetall(session_key)
        return data or None

    async def get_user_sessions(self, user_id: str) -> list[dict[str, str]]:
        session_ids = await self._redis.smembers(self._user_sessions_key(user_id))
        result: list[dict[str, str]] = []

        for session_id in session_ids:
            data = await self.get_session_tokens(session_id)
            if not data:
                continue
            data["session_id"] = session_id
            result.append(data)

        result.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return result

    async def touch_session(self, session_id: str) -> None:
        session_key = self._session_key(session_id)
        await self._redis.hset(
            session_key,
            mapping={"last_seen_at": datetime.now(timezone.utc).isoformat()},
        )

    async def delete_session(self, session_id: str) -> None:
        session_key = self._session_key(session_id)
        user_id = await self._redis.hget(session_key, "user_id")
        await self._redis.delete(session_key)
        if user_id:
            await self._redis.srem(self._user_sessions_key(user_id), session_id)

    async def delete_other_sessions(self, user_id: str, current_session_id: str) -> int:
        session_ids = await self._redis.smembers(self._user_sessions_key(user_id))
        removed = 0

        for session_id in session_ids:
            if session_id == current_session_id:
                continue
            await self.delete_session(session_id)
            removed += 1

        return removed
    async def publish_event(self, channel: str, event_type: str, data: dict) -> None:
        """Публикует событие в Redis канал."""
        message = json.dumps({
            "event": event_type,
            "data": data
        })
        await self._redis.publish(channel, message)

    async def publish(self, channel: str, message: str) -> None:
        await self._redis.publish(channel, message)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_PREFIX = os.getenv("REDIS_PREFIX", "messenger")

redis_client = RedisClient(redis_url=REDIS_URL, key_prefix=REDIS_PREFIX)
