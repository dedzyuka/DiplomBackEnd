import hashlib
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
from services.models import User,SessionEvent


class AuthServicer(mess_pb2_grpc.AuthServiceServicer):
    def __init__(self):
        self.secret_key = os.getenv("SECRET_KEY", "change-me-in-production")
        self.algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        self.access_ttl_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
        self.refresh_ttl_days = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
        self.issuer = os.getenv("JWT_ISSUER", "messenger-backend")
        self.audience = os.getenv("JWT_AUDIENCE", "messenger-clients")

    def _encode_token(self, sub: str, token_type: str, expires_at: datetime, session_id: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": sub,
            "sid": session_id,
            "iss": self.issuer,
            "aud": self.audience,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": str(uuid4()),
            "type": token_type,
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def _new_access(self, user_id: str, session_id: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=self.access_ttl_minutes)
        return self._encode_token(user_id, "access", expire, session_id)

    def _new_refresh(self, user_id: str, session_id:str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(days=self.refresh_ttl_days)
        return self._encode_token(user_id, "refresh", expire, session_id)
    
    async def _decode_token_or_abort(self, token: str, expected_type: str, context) -> dict:
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                audience=self.audience,
                issuer=self.issuer,
            )
        except Exception:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, f"Invalid {expected_type} token")

        if payload.get("type") != expected_type:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, f"Invalid {expected_type} token type")
        
        return payload
    
    def _extract_request_meta(self, context) -> tuple[str | None, str | None, str | None]:
        ip_address = None
        peer = context.peer() if context else None
        if peer:
            ip_address = peer.split(":")[-1]

        user_agent = None
        device_info = None
        metadata = context.invocation_metadata() if context else None
        if metadata:
            for item in metadata:
                key = (item.key or "").lower()
                if key in {"user-agent", "x-user-agent"}:
                    user_agent = item.value
                if key in {"x-device", "x-device-info"}:
                    device_info = item.value

        return ip_address, user_agent, device_info

    async def _log_session_event(self, *, user_id: str, action: str, refresh_token: str | None, context) -> None:
        refresh_token_hash = None
        if refresh_token:
            refresh_token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()

        ip_address, user_agent, device_info = self._extract_request_meta(context)

        async with AsyncSessionLocal() as audit_session:
            audit_session.add(
                SessionEvent(
                    user_id=user_id,
                    action=action,
                    refresh_token_hash=refresh_token_hash,
                    device_info=device_info,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
            await audit_session.commit()

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
            session_id = str(uuid4())
            access_token = self._new_access(user_id, session_id)
            refresh_token = self._new_refresh(user_id, session_id)
            await redis_client.set_session_tokens(
                session_id=session_id,
                user_id=user_id,
                refresh_token=refresh_token,
                access_token=access_token,
                ttl_seconds=self.refresh_ttl_days * 24 * 60 * 60,
            )

            await self._log_session_event(
                user_id=user_id,
                action="login",
                refresh_token=refresh_token,
                context=context,
            )


            return mess_pb2.LoginResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=self.access_ttl_minutes * 60,
                user=db_user_to_proto(user),
            )

    async def RefreshToken(self, request, context):
        refresh_token = request.refresh_token
        payload = await self._decode_token_or_abort(refresh_token, expected_type="refresh", context=context)

        user_id = payload["sub"]
        session_id = payload["sid"]

        user_id = payload.get("sub")
        
        stored_session = await redis_client.get_session_tokens(session_id)
        if not stored_session:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Session not found or revoked")

        if stored_session.get("user_id") != user_id:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Session user mismatch")

        if stored_session.get("refresh_token") != refresh_token:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Refresh token revoked")

        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if not user:
                await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")

            new_access = self._new_access(user_id, session_id)
            await redis_client.set_session_tokens(
                session_id=session_id,
                user_id=user_id,
                refresh_token=refresh_token,
                access_token=new_access,
                ttl_seconds=self.refresh_ttl_days * 24 * 60 * 60,
            )
            await self._log_session_event(
                user_id=user_id,
                action="refresh",
                refresh_token=refresh_token,
                context=context,
            )

            return mess_pb2.LoginResponse(
                access_token=new_access,
                refresh_token=refresh_token,
                expires_in=self.access_ttl_minutes * 60,
                user=db_user_to_proto(user),
            )

    async def Logout(self, request, context):
        refresh_token = request.refresh_token
        try:
            payload = await self._decode_token_or_abort(refresh_token, expected_type="refresh", context=context)
        except Exception:
            return Empty()

        session_id = payload.get("sid")
        if session_id:
            stored_session = await redis_client.get_session_tokens(session_id)
            if stored_session and stored_session.get("refresh_token") == refresh_token:
                await redis_client.delete_session(session_id)
                await self._log_session_event(
                    user_id=payload.get("sub"),
                    action="logout",
                    refresh_token=refresh_token,
                    context=context,
                )

        return Empty()