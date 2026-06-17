# from fastapi import FastAPI
# from app.FastApiClient.api.endpoints import auth, users, chats, messages, contacts, admin

# app = FastAPI(title="Messenger API", version="1.0.0")

# # Подключаем роутеры
# app.include_router(auth.router)
# app.include_router(users.router)
# app.include_router(chats.router)
# app.include_router(messages.router)  # обрати внимание: этот роутер уже включает префикс /chats/{chat_id}/messages
# app.include_router(contacts.router)
# app.include_router(admin.router)

# @app.get("/health")
# async def health():
#     return {"status": "ok"}

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from strawberry.fastapi import GraphQLRouter
from FastApiClient.graphql.schema import schema
from FastApiClient.graphql.context import get_context
from FastApiClient.api.endpoints import upload
from FastApiClient.api.endpoints.push import router as push_router
import httpx
from fastapi import Response
from FastApiClient.core.config import settings


app = FastAPI(title="FastAPI + GraphQL + gRPC (nested groups)")

# Настройка GraphQL роутера
graphql_app = GraphQLRouter(
    schema,
    context_getter=get_context,
    graphql_ide="graphiql"  # Можно также "apollo-sandbox"
)

app.include_router(graphql_app, prefix="/graphql")
app.include_router(upload.router)
app.include_router(push_router)

@app.get("/")
async def root():
    return {"message": "Welcome to FastAPI GraphQL gRPC example"}

@app.get("/media/{path:path}")
async def get_media(request: Request, path: str):
    minio_url = f"{settings.MINIOPUBLICURL}/{settings.MINIOBUCKET}/{path}"
    headers = {}
    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    async with httpx.AsyncClient() as client:
        resp = await client.get(minio_url, headers=headers, follow_redirects=True)
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="File not found")

    return StreamingResponse(
        resp.aiter_bytes(),
        status_code=resp.status_code,
        headers={
            "Content-Type": resp.headers.get("content-type", "audio/m4a"),
            "Content-Length": resp.headers.get("content-length", ""),
            "Accept-Ranges": "bytes",
            "Content-Range": resp.headers.get("content-range", ""),
        },
    )