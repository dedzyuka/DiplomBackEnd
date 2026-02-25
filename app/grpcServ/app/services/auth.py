import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import grpc
from google.protobuf.empty_pb2 import Empty
from jose import jwt
from sqlalchemy import or_, select

from database import AsyncSessionLocal
from protobuf import mess_pb2, mess_pb2_grpc
from services.redis_client import redis_client
from security.NewPass import CreatePass
from services.converters.userConverter import db_user_to_proto
from services.models import User


class AuthServicer(mess_pb2_grpc.AuthServiceServicer):
    def __init__(self):
        self.secret_key = os.getenv("SECRET_KEY", "change-me-in-production")
        self.algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        self.access_ttl_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
        self.refresh_ttl_days = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
        self.issuer = os.getenv("JWT_ISSUER", "messenger-backend")
        self.audience = os.getenv("JWT_AUDIENCE", "messenger-clients")

    def _encode_token(self, sub: str, token_type: str, expires_at: datetime) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": sub,
            "iss": self.issuer,
            "aud": self.audience,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": str(uuid4()),
            "type": token_type,
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def _new_access(self, user_id: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=self.access_ttl_minutes)
        return self._encode_token(user_id, "access", expire)

    def _new_refresh(self, user_id: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(days=self.refresh_ttl_days)
        return self._encode_token(user_id, "refresh", expire)

    async def Login(self, request, context):
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(
                or_(
                    User.nick_name == request.login,
                    User.email == request.login,
                    User.phone == request.login,
                )
            )
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid credentials")

            if not CreatePass.VerifyPass(request.password, user.salt, user.password_hash):
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid credentials")

            user_id = str(user.user_id)
            access_token = self._new_access(user_id)
            refresh_token = self._new_refresh(user_id)
            await redis_client.set_refresh_token(
                user_id=user_id,
                refresh_token=refresh_token,
                ttl_seconds=self.refresh_ttl_days * 24 * 60 * 60,
            )

            return mess_pb2.LoginResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=self.access_ttl_minutes * 60,
                user=db_user_to_proto(user),
            )

    async def RefreshToken(self, request, context):
        refresh_token = request.refresh_token
        try:
            payload = jwt.decode(
                refresh_token,
                self.secret_key,
                algorithms=[self.algorithm],
                audience=self.audience,
                issuer=self.issuer,
            )
        except Exception:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid refresh token")

        if payload.get("type") != "refresh":
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid refresh token type")

        user_id = payload.get("sub")
        if not user_id:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid refresh token payload")

        stored_refresh = await redis_client.get_refresh_token(user_id)
        if stored_refresh != refresh_token:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Refresh token revoked")

        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if not user:
                await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")

            new_access = self._new_access(user_id)
            new_refresh = self._new_refresh(user_id)
            await redis_client.set_refresh_token(
                user_id=user_id,
                refresh_token=new_refresh,
                ttl_seconds=self.refresh_ttl_days * 24 * 60 * 60,
            )

            return mess_pb2.LoginResponse(
                access_token=new_access,
                refresh_token=new_refresh,
                expires_in=self.access_ttl_minutes * 60,
                user=db_user_to_proto(user),
            )

    async def Logout(self, request, context):
        refresh_token = request.refresh_token
        try:
            payload = jwt.decode(
                refresh_token,
                self.secret_key,
                algorithms=[self.algorithm],
                audience=self.audience,
                issuer=self.issuer,
            )
        except Exception:
            return Empty()

        user_id = payload.get("sub")
        if user_id:
            stored_refresh = await redis_client.get_refresh_token(user_id)
            if stored_refresh == refresh_token:
                await redis_client.delete_refresh_token(user_id)

        return Empty()