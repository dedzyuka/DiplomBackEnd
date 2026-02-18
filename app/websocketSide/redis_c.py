from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4
from fastapi import FastAPI, Depends, Request
from typing import Annotated, Optional
from pydantic import ConfigDict, Field
import redis.asyncio as redis
from uuid import UUID

from app.FastApiClient.schemas import MessageBase, MessageCreate, MessageResponse



class RedisClient:
    def __init__(self, url="redis://localhost:6379/0"):
        self.url = url
        self.client = None
    
    async def create(self):
        pool = redis.ConnectionPool.from_url(
            self.url,
            decode_responses=True,
            max_connections=20
        )
        self.client = redis.Redis(connection_pool=pool)
    
    async def close(self):
        if self.client:
            await self.client.aclose()
    
    async def get_key(self, key: str) -> str:
        return await self.client.get(key)
    
    async def set_key_with_ttl(self, key: str, value: str, ttl: int) -> bool:
        return bool(await self.client.setex(key, ttl, value))
    
    # async def add_online_user(self) -> bool:
    #     val =  await self.client.get("online_users")
    #     print(val)
    #     val = int(val)

    #     if val is not None:
    #         val+=1
    #         return bool(await self.client.set(key = "online_users", value = str(val)))
    #     else:
    #         return "Exp"
    async def add_online_user_count(self) -> bool:
        return await self.client.incr("online_users_count")

        
    async def del_online_user_count(self) -> bool:

        return await self.client.decr("online_users_count")
        # val =  await self.client.get("online_users")

        # if bool(val):
        #     val= int(val)
        #     val+=1
        #     return bool(await self.client.hset("online_users", val))
        # else:
        #     return "Exp"

    async def add_online_user(self, value: str) -> bool:

        return await self.client.sadd("project:online_users",value)

        
    async def del_online_user(self,value:str) -> bool:

        return await self.client.srem("project:online_users",value)
    
    async def existOfflineMess(self, key:str):
        return await self.client.exists(key)
    async def createOfflineMess(self, key:str):
        await self.client.lpush(f"OfflineMessFor : {key}","1")
        return await self.client.lpop(f"OfflineMessFor : {key}")
    async def userIsOnline(self, user: str):
        return await self.client.sismember("project:online_users", user)
    async def addOfflineMess(self, name: str, ):

        await self.client.lpush()
    async def saveOfflineMess(self, offMess: str, sender_id:str, recipient:str):
        key = f"OfflineMessFor : {recipient.strip()}"
        print(type(sender_id))
        return await self.client.lpush(key, offMess)
    async def deleteOfflineMess(self, key:str):
        raw_messages = await self.client.lrange(f"OfflineMessFor : {key.strip()}", 0, -1)
        print(raw_messages)
        await self.client.ltrim(f"OfflineMessFor : {key.strip()}", 1, 0)

        return raw_messages


# --- LIFESPAN ---
@asynccontextmanager
async def redis_lifespan(app: FastAPI):
    redis_client = RedisClient()
    await redis_client.create()
    app.state.redis_client = redis_client
    yield
    await redis_client.close()

# --- ПЕРЕДАЁМ LIFESPAN В FASTAPI ---
app = FastAPI(lifespan=redis_lifespan)   # 🔥 ключевая строка

# --- DEPENDENCY ---
async def get_redis_client(request: Request) -> RedisClient:
    return request.app.state.redis_client



# --- РОУТЫ ---
# @app.get("/key/{key}")
# async def get_key(key: str, r: RedisClientDep):
#     value = await r.get_key(key)
#     return {"key": key, "value": value}


# class OfflineMess:
#     user_id :str
#     refresh_token_hash : str
#     device_info:str
#     ip : str
#     user_agent:str
#     created_at:str
#     xpires_at:str

from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from datetime import datetime
from typing import Optional
from app.FastApiClient.enums import MessageType  

# ---------- Базовые поля сообщения (общие) ----------
class MessageBase(BaseModel):
    content: Optional[str] = None
    type: MessageType = MessageType.text
    metadata: Optional[dict] = None
    reply_to_id: Optional[int] = None

# ---------- Схема для входящего сообщения (от клиента) ----------
class MessageIn(MessageBase):
    """Клиент обязан передать chat_id и sender_id (UUID)."""
    chat_id: UUID
    sender_id: UUID

    # Если нужно, можно добавить поля для временных меток (например, client_created_at)
    # но они не обязательны, так как сервер сам проставит created_at.

# ---------- Схема для исходящего сообщения (от сервера) ----------
class MessageOut(MessageBase):
    """Полная информация о сообщении, которую сервер отправляет клиентам."""
    message_id: int              # или UUID, смотрите по БД
    chat_id: UUID
    sender_id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    is_edited: bool = False

    model_config = ConfigDict(from_attributes=True)  # для работы с ORM
    


