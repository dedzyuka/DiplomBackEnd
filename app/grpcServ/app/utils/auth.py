import grpc
import jwt
import os


async def get_current_user_id(context) -> str:
    """
    Асинхронно извлекает ID пользователя из метаданных gRPC-запроса.
    При ошибке аутентификации вызывает context.abort().
    """
    metadata = context.invocation_metadata() if context else None
    auth_header = None
    forwarded_user_id = None

    if metadata:
        for item in metadata:
            key = (item.key or "").lower()
            if key == "authorization":
                auth_header = item.value
            elif key in {"x-user-id", "user-id"}:
                forwarded_user_id = item.value

    if auth_header:
        token = auth_header.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()

        if token:
            try:
                secret_key = os.getenv("SECRET_KEY", "change-me-in-production")
                algorithm = os.getenv("JWT_ALGORITHM", "HS256")
                issuer = os.getenv("JWT_ISSUER", "messenger-backend")
                audience = os.getenv("JWT_AUDIENCE", "messenger-clients")

                payload = jwt.decode(
                    token,
                    secret_key,
                    algorithms=[algorithm],
                    audience=audience,
                    issuer=issuer,
                )
                if payload.get("type") == "access":
                    sub = payload.get("sub")
                    if sub:
                        return str(sub)
            except Exception:
                if forwarded_user_id:
                    return forwarded_user_id
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid or expired token")

    if forwarded_user_id:
        return forwarded_user_id

    await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing authentication credentials")