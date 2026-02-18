from fastapi import FastAPI
from app.FastApiClient.api.endpoints import auth, users, chats, messages, contacts, admin

app = FastAPI(title="Messenger API", version="1.0.0")

# Подключаем роутеры
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(chats.router)
app.include_router(messages.router)  # обрати внимание: этот роутер уже включает префикс /chats/{chat_id}/messages
app.include_router(contacts.router)
app.include_router(admin.router)

@app.get("/health")
async def health():
    return {"status": "ok"}