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

from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter
from FastApiClient.graphql.schema import schema
from FastApiClient.graphql.context import get_context
from FastApiClient.api.endpoints import upload


app = FastAPI(title="FastAPI + GraphQL + gRPC (nested groups)")

# Настройка GraphQL роутера
graphql_app = GraphQLRouter(
    schema,
    context_getter=get_context,
    graphql_ide="graphiql"  # Можно также "apollo-sandbox"
)

app.include_router(graphql_app, prefix="/graphql")
app.include_router(upload.router)

@app.get("/")
async def root():
    return {"message": "Welcome to FastAPI GraphQL gRPC example"}
