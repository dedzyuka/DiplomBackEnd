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

from google.protobuf.timestamp_pb2 import Timestamp
from services.access_session import resolve_access_session


from core.config import settings

class AuthServicer(mess_pb2_grpc.AuthServiceServicer):
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.access_ttl_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_ttl_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
        self.issuer = settings.JWT_ISSUER
        self.audience = settings.JWT_AUDIENCE

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
            now = datetime.now(timezone.utc)

            device_info = request.device_info or self._metadata_value(context, "x-device-info")
            ip_address = request.ip_address or self._metadata_value(context, "x-forwarded-for")
            user_agent = request.user_agent or self._metadata_value(context, "x-user-agent")

            await redis_client.set_session_tokens(
                session_id=session_id,
                user_id=str(user.user_id),
                refresh_token=refresh_token,
                access_token=access_token,
                ttl_seconds=self.refresh_ttl_days * 24 * 60 * 60,
                device_info=device_info,
                ip_address=ip_address,
                user_agent=user_agent,
                created_at=now,
                last_seen_at=now,
            )

            await self._log_session_event(
                user_id=str(user.user_id),
                action="login",
                refresh_token=refresh_token,
                context=context,
                device_info=device_info,
                ip_address=ip_address,
                user_agent=user_agent,
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
            user_id=str(user.user_id),
            refresh_token=refresh_token,
            access_token=new_access,
            ttl_seconds=self.refresh_ttl_days * 24 * 60 * 60,
            device_info=stored_session.get("device_info"),
            ip_address=stored_session.get("ip_address"),
            user_agent=stored_session.get("user_agent"),
            created_at=self._parse_iso_dt(stored_session.get("created_at")) or datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            )
            await self._log_session_event(
            user_id=str(user.user_id),
            action="refresh",
            refresh_token=refresh_token,
            context=context,
            device_info=stored_session.get("device_info"),
            ip_address=stored_session.get("ip_address"),
            user_agent=stored_session.get("user_agent"),
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
    
    async def ListSessions(self, request, context):
        principal = await self._require_access_principal(context)

        sessions = await redis_client.get_user_sessions(principal.user_id)
        items = [
            self._session_info_from_redis(item, principal.session_id)
            for item in sessions
        ]

        return mess_pb2.ListSessionsResponse(sessions=items)

    async def LogoutCurrentSession(self, request, context):
        principal = await self._require_access_principal(context)

        await redis_client.delete_session(principal.session_id)
        await self._log_session_event(
            user_id=principal.user_id,
            action="logout",
            refresh_token=None,
            context=context,
        )
        return Empty()

    async def RevokeSession(self, request, context):
        principal = await self._require_access_principal(context)

        target_session_id = (request.session_id or "").strip()
        if not target_session_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "session_id is required")

        target_session = await redis_client.get_session_tokens(target_session_id)
        if not target_session:
            return Empty()

        if target_session.get("user_id") != principal.user_id:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Cannot revoke чужую сессию")

        await redis_client.delete_session(target_session_id)
        await self._log_session_event(
            user_id=principal.user_id,
            action="revoke",
            refresh_token=None,
            context=context,
            device_info=target_session.get("device_info"),
            ip_address=target_session.get("ip_address"),
            user_agent=target_session.get("user_agent"),
        )
        return Empty()

    async def LogoutAllOtherSessions(self, request, context):
        principal = await self._require_access_principal(context)

        await redis_client.delete_other_sessions(
            principal.user_id,
            principal.session_id,
        )

        await self._log_session_event(
            user_id=principal.user_id,
            action="logout_others",
            refresh_token=None,
            context=context,
        )
        return Empty()


    @staticmethod
    def _metadata_value(context, key: str) -> str | None:
        metadata = context.invocation_metadata() if context else None
        if not metadata:
            return None

        lookup = key.lower()
        for item in metadata:
            if (item.key or "").lower() == lookup:
                value = (item.value or "").strip()
                return value or None
        return None

    @staticmethod
    def _dt_to_ts(dt: datetime | None) -> Timestamp:
        ts = Timestamp()
        if dt is None:
            return ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ts.FromDatetime(dt)
        return ts

    @staticmethod
    def _parse_iso_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            normalized = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    async def _require_access_principal(self, context):
        principal = await resolve_access_session(context)
        if not principal:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid or revoked access session")
        return principal

    async def _log_session_event(
        self,
        *,
        user_id: str | None,
        action: str,
        refresh_token: str | None,
        context,
        device_info: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        if not user_id:
            return

        refresh_token_hash = None
        if refresh_token:
            refresh_token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()

        if device_info is None:
            device_info = self._metadata_value(context, "x-device-info")
        if ip_address is None:
            ip_address = self._metadata_value(context, "x-forwarded-for")
        if user_agent is None:
            user_agent = self._metadata_value(context, "x-user-agent")

        try:
            async with AsyncSessionLocal() as session:
                session.add(
                    SessionEvent(
                        user_id=user_id,
                        action=action,
                        refresh_token_hash=refresh_token_hash,
                        device_info=device_info,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                )
                await session.commit()
        except Exception:
            # аудит не должен валить auth flow
            pass

    def _session_info_from_redis(self, data: dict[str, str], current_session_id: str) -> mess_pb2.SessionInfo:
        created_at = self._parse_iso_dt(data.get("created_at"))
        last_seen_at = self._parse_iso_dt(data.get("last_seen_at"))

        info = mess_pb2.SessionInfo(
            session_id=data.get("session_id", ""),
            device_info=data.get("device_info", ""),
            ip_address=data.get("ip_address", ""),
            user_agent=data.get("user_agent", ""),
            created_at=self._dt_to_ts(created_at),
            is_current=data.get("session_id") == current_session_id,
        )

        if last_seen_at is not None:
            info.last_seen_at.CopyFrom(self._dt_to_ts(last_seen_at))

        return info