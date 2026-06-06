from datetime import datetime, timezone
import uuid

import grpc
from google.protobuf.empty_pb2 import Empty
from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from services.redis_client import redis_client
from database import AsyncSessionLocal
from protobuf import mess_pb2, mess_pb2_grpc
from security.NewPass import CreatePass
from services.access_session import require_current_user_id
from services.converters.userConverter import db_user_to_proto
from services.enums import AccountStatus as DbAccountStatus
from services.enums import PrivacyLevel as DbPrivacyLevel
from services.models import PrivacySetting, User
from google.protobuf.timestamp_pb2 import Timestamp


class UsersServicer(mess_pb2_grpc.UserServiceServicer):
    _PRIVACY_PROTO_TO_DB = {
        1: DbPrivacyLevel.everyone,
        2: DbPrivacyLevel.contacts,
        3: DbPrivacyLevel.nobody,
    }

    _PRIVACY_DB_TO_PROTO = {
        "everyone": 1,
        "contacts": 2,
        "nobody": 3,
    }

    async def _require_current_user_id(self, context) -> str:
        return await require_current_user_id(context)

    @staticmethod
    def _normalize_query(query: str) -> str:
        raw = (query or "").strip()
        if raw.startswith("@"):
            raw = raw[1:]
        return raw

    async def _get_or_create_privacy(self, session, user_id):
        stmt = select(PrivacySetting).where(PrivacySetting.user_id == user_id)
        privacy = (await session.execute(stmt)).scalar_one_or_none()

        if privacy:
            return privacy

        privacy = PrivacySetting(
            user_id=user_id,
            who_can_write_me=DbPrivacyLevel.everyone,
            who_can_add_to_groups=DbPrivacyLevel.everyone,
            who_can_see_phone=DbPrivacyLevel.contacts,
            who_can_see_last_seen=DbPrivacyLevel.everyone,
        )
        session.add(privacy)
        await session.flush()
        return privacy

    async def CreateUser(self, request, context):
        user_data = {
            "nick_name": (request.nick_name or "").strip(),
            "first_name": (request.first_name or "").strip() or None,
            "last_name": (request.last_name or "").strip() or None,
            "middle_name": (request.middle_name or "").strip() or None,
            "email": (request.email or "").strip() or None,
            "phone": (request.phone or "").strip() or None,
            "password": request.password,
        }

        if not user_data["nick_name"]:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "nick_name is required")
        if not user_data["password"]:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "password is required")

        password_hash, salt = CreatePass.createPassWithSalt(password=user_data["password"])

        async with AsyncSessionLocal() as session:
            try:
                stmt = (
                    insert(User)
                    .values(
                        nick_name=user_data["nick_name"],
                        first_name=user_data["first_name"],
                        last_name=user_data["last_name"],
                        middle_name=user_data["middle_name"],
                        email=user_data["email"],
                        phone=user_data["phone"],
                        password_hash=password_hash,
                        salt=salt,
                    )
                    .returning(User)
                )
                result = await session.execute(stmt)
                new_user = result.scalar_one()

                session.add(
                    PrivacySetting(
                        user_id=new_user.user_id,
                        who_can_write_me=DbPrivacyLevel.everyone,
                        who_can_add_to_groups=DbPrivacyLevel.everyone,
                        who_can_see_phone=DbPrivacyLevel.contacts,
                        who_can_see_last_seen=DbPrivacyLevel.everyone,
                    )
                )

                await session.commit()
                return db_user_to_proto(new_user)
            except IntegrityError:
                await session.rollback()
                await context.abort(
                    grpc.StatusCode.ALREADY_EXISTS,
                    "User with provided nick_name, email or phone already exists",
                )
            except Exception as e:
                await session.rollback()
                await context.abort(grpc.StatusCode.INTERNAL, f"CreateUser failed: {e}")

    async def GetUser(self, request, context):
        user_id = (request.user_id or "").strip()
        if not user_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is required")

        try:
            user_uuid = uuid.UUID(user_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid user_id")

        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_uuid)
            if not user or user.status == DbAccountStatus.deleted:
                await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")

            is_online = await redis_client.is_user_online(str(user.user_id))
            proto_user = db_user_to_proto(user)
            proto_user.is_online = is_online   # переопределяем
            return proto_user

    async def UpdateUser(self, request, context):
        user_id = (request.user_id or "").strip()
        if not user_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is required")

        current_user_id = await self._require_current_user_id(context)
        if current_user_id != user_id:
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "Cannot update another user",
            )

        try:
            user_uuid = uuid.UUID(user_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid user_id")

        update_data = {}
        if request.nick_name:
            update_data["nick_name"] = request.nick_name.strip()
        if request.first_name:
            update_data["first_name"] = request.first_name.strip()
        if request.last_name:
            update_data["last_name"] = request.last_name.strip()
        if request.middle_name:
            update_data["middle_name"] = request.middle_name.strip()
        if request.email:
            update_data["email"] = request.email.strip()
        if request.phone:
            update_data["phone"] = request.phone.strip()
        if request.avatar_url:
            update_data["avatar_url"] = request.avatar_url.strip()
        if request.avatar_url:
            update_data["avatar_url"] = request.avatar_url.lower()
        if request.bio:
            update_data["bio"] = request.bio.strip()

        if not update_data:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "No fields to update")

        update_data["updated_at"] = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as session:
            try:
                stmt = (
                    update(User)
                    .where(User.user_id == user_uuid)
                    .values(**update_data)
                    .returning(User)
                )
                result = await session.execute(stmt)
                updated_user = result.scalar_one_or_none()

                if not updated_user or updated_user.status == DbAccountStatus.deleted:
                    await session.rollback()
                    await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")

                await session.commit()
                return db_user_to_proto(updated_user)
            except IntegrityError:
                await session.rollback()
                await context.abort(
                    grpc.StatusCode.ALREADY_EXISTS,
                    "nick_name, email or phone already exists",
                )
            except Exception as e:
                await session.rollback()
                await context.abort(grpc.StatusCode.INTERNAL, f"UpdateUser failed: {e}")

    async def DeleteUser(self, request, context):
        user_id = (request.user_id or "").strip()
        if not user_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is required")

        current_user_id = await self._require_current_user_id(context)
        if current_user_id != user_id:
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "Cannot delete another user",
            )

        try:
            user_uuid = uuid.UUID(user_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid user_id")

        async with AsyncSessionLocal() as session:
            stmt = (
                update(User)
                .where(User.user_id == user_uuid)
                .values(
                    status=DbAccountStatus.deleted,
                    is_online=False,
                    updated_at=datetime.now(timezone.utc),
                )
                .returning(User)
            )
            result = await session.execute(stmt)
            deleted_user = result.scalar_one_or_none()

            if not deleted_user:
                await session.rollback()
                await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")

            await session.commit()
            return Empty()

    async def SearchUsers(self, request, context):
        query = self._normalize_query(request.query)
        page_size = max(1, request.page_size or 20)

        try:
            offset = int(request.page_token or "0")
        except ValueError:
            offset = 0

        async with AsyncSessionLocal() as session:
            stmt = (
                select(User)
                .where(
                    User.status != DbAccountStatus.deleted,
                    User.nick_name.ilike(f"%{query}%") if query else True,
                )
                .order_by(User.nick_name.asc())
                .offset(offset)
                .limit(page_size)
            )

            users = (await session.execute(stmt)).scalars().all()

            next_offset = offset + len(users)
            next_page_token = str(next_offset) if len(users) == page_size else ""

            return mess_pb2.UsersListResponse(
                users=[db_user_to_proto(user) for user in users],
                next_page_token=next_page_token,
            )

    async def GetMyProfile(self, request, context):
        current_user_id = await self._require_current_user_id(context)

        try:
            user_uuid = uuid.UUID(current_user_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid current user id")

        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_uuid)
            if not user or user.status == DbAccountStatus.deleted:
                await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")
            return db_user_to_proto(user)

    def _privacy_to_proto_value(self, value) -> int:
        raw = getattr(value, "value", value)
        return self._PRIVACY_DB_TO_PROTO.get(
            str(raw),
            mess_pb2.PrivacyLevel.PRIVACY_LEVEL_UNSPECIFIED,
        )

    def _db_privacy_to_proto(self, db_privacy: PrivacySetting) -> mess_pb2.PrivacySetting:
        response = mess_pb2.PrivacySetting(
            user_id=str(db_privacy.user_id),
            who_can_write_me=self._privacy_to_proto_value(db_privacy.who_can_write_me),
            who_can_add_to_groups=self._privacy_to_proto_value(db_privacy.who_can_add_to_groups),
            who_can_see_phone=self._privacy_to_proto_value(db_privacy.who_can_see_phone),
            who_can_see_last_seen=self._privacy_to_proto_value(db_privacy.who_can_see_last_seen),
        )

        if db_privacy.updated_at:
            ts = Timestamp()
            ts.FromDatetime(db_privacy.updated_at)
            response.updated_at.CopyFrom(ts)

        return response

    async def UpdatePrivacy(self, request, context):
        user_id = (request.user_id or "").strip()
        if not user_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is required")

        current_user_id = await self._require_current_user_id(context)
        if current_user_id != user_id:
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "Cannot update privacy for another user",
            )

        try:
            user_uuid = uuid.UUID(user_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid user_id")

        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_uuid)
            if not user or user.status == DbAccountStatus.deleted:
                await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")

            privacy = await self._get_or_create_privacy(session, user_uuid)

            changed = False

            if request.HasField("who_can_write_me") and request.who_can_write_me in self._PRIVACY_PROTO_TO_DB:
                privacy.who_can_write_me = self._PRIVACY_PROTO_TO_DB[request.who_can_write_me]
                changed = True

            if request.HasField("who_can_add_to_groups") and request.who_can_add_to_groups in self._PRIVACY_PROTO_TO_DB:
                privacy.who_can_add_to_groups = self._PRIVACY_PROTO_TO_DB[request.who_can_add_to_groups]
                changed = True

            if request.HasField("who_can_see_phone") and request.who_can_see_phone in self._PRIVACY_PROTO_TO_DB:
                privacy.who_can_see_phone = self._PRIVACY_PROTO_TO_DB[request.who_can_see_phone]
                changed = True

            if request.HasField("who_can_see_last_seen") and request.who_can_see_last_seen in self._PRIVACY_PROTO_TO_DB:
                privacy.who_can_see_last_seen = self._PRIVACY_PROTO_TO_DB[request.who_can_see_last_seen]
                changed = True

            if not changed:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "No privacy fields to update")

            privacy.updated_at = datetime.now(timezone.utc)

            await session.commit()
            await session.refresh(privacy)

            return self._db_privacy_to_proto(privacy)

    async def GetMyPrivacy(self, request, context):
        current_user_id = await self._require_current_user_id(context)

        try:
            user_uuid = uuid.UUID(current_user_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid current user id")

        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_uuid)
            if not user or user.status == DbAccountStatus.deleted:
                await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")

            privacy = await self._get_or_create_privacy(session, user_uuid)
            await session.commit()
            await session.refresh(privacy)

            return self._db_privacy_to_proto(privacy)