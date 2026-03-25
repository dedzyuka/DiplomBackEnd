from datetime import datetime, timezone

import grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy import delete, insert, or_, select, update

from database import AsyncSessionLocal
from protobuf import mess_pb2, mess_pb2_grpc
from security.NewPass import CreatePass
from services.access_session import require_current_user_id
from services.converters.userConverter import db_user_to_proto
from services.models import PrivacySetting, User


class UsersServicer(mess_pb2_grpc.UserServiceServicer):
    async def _require_current_user_id(self, context) -> str:
        return await require_current_user_id(context)

    async def CreateUser(self, request, context):
        user_data = {
            "nick_name": request.nick_name,
            "first_name": request.first_name,
            "last_name": request.last_name,
            "middle_name": request.middle_name,
            "email": request.email,
            "phone": request.phone,
            "password": request.password,
        }

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
                await session.commit()
                return db_user_to_proto(new_user)
            except Exception as e:
                await session.rollback()
                await context.abort(grpc.StatusCode.INTERNAL, f"CreateUser failed: {e}")

    async def GetUser(self, request, context):
        user_id = request.user_id
        if not user_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is required")

        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if not user:
                await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")
            return db_user_to_proto(user)

    async def UpdateUser(self, request, context):
        user_id = request.user_id
        if not user_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is required")

        current_user_id = await self._require_current_user_id(context)
        if current_user_id != str(user_id):
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "Cannot update another user",
            )

        update_data = {}
        if request.nick_name:
            update_data["nick_name"] = request.nick_name
        if request.first_name:
            update_data["first_name"] = request.first_name
        if request.last_name:
            update_data["last_name"] = request.last_name
        if request.middle_name:
            update_data["middle_name"] = request.middle_name
        if request.email:
            update_data["email"] = request.email
        if request.phone:
            update_data["phone"] = request.phone
        if request.avatar_url:
            update_data["avatar_url"] = request.avatar_url
        if request.bio:
            update_data["bio"] = request.bio

        async with AsyncSessionLocal() as session:
            try:
                if not update_data:
                    user = await session.get(User, user_id)
                    if not user:
                        await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")
                    return db_user_to_proto(user)

                stmt = (
                    update(User)
                    .where(User.user_id == user_id)
                    .values(**update_data)
                    .returning(User)
                )
                result = await session.execute(stmt)
                updated_user = result.scalar_one_or_none()
                if not updated_user:
                    await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")

                await session.commit()
                return db_user_to_proto(updated_user)
            except Exception as e:
                await session.rollback()
                await context.abort(grpc.StatusCode.INTERNAL, f"UpdateUser failed: {e}")

    async def DeleteUser(self, request, context):
        user_id = request.user_id
        if not user_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is required")

        current_user_id = await self._require_current_user_id(context)
        if current_user_id != str(user_id):
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "Cannot delete another user",
            )

        async with AsyncSessionLocal() as session:
            stmt = delete(User).where(User.user_id == user_id)
            result = await session.execute(stmt)
            await session.commit()
            if result.rowcount == 0:
                await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")
            return Empty()

    async def SearchUsers(self, request, context):
        query = request.query or ""
        page_size = request.page_size or 20
        page_size = max(1, min(page_size, 100))

        offset = 0
        if request.page_token:
            try:
                offset = int(request.page_token)
            except ValueError:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid page_token")

        async with AsyncSessionLocal() as session:
            stmt = (
                select(User)
                .where(
                    or_(
                        User.nick_name.ilike(f"%{query}%"),
                        User.email.ilike(f"%{query}%"),
                        User.phone.ilike(f"%{query}%"),
                    )
                )
                .offset(offset)
                .limit(page_size + 1)
            )
            result = await session.execute(stmt)
            rows = list(result.scalars().all())

            has_next = len(rows) > page_size
            users = rows[:page_size]
            next_token = str(offset + page_size) if has_next else ""

            return mess_pb2.UsersListResponse(
                users=[db_user_to_proto(u) for u in users],
                next_page_token=next_token,
                total_count=offset + len(users),
            )

    async def GetMyProfile(self, request, context):
        current_user_id = await self._require_current_user_id(context)

        async with AsyncSessionLocal() as session:
            user = await session.get(User, current_user_id)
            if not user:
                await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")
            return db_user_to_proto(user)

    async def UpdatePrivacy(self, request, context):
        current_user_id = await self._require_current_user_id(context)
        if current_user_id != str(request.user_id):
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "Cannot update another user's privacy settings",
            )

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PrivacySetting).where(PrivacySetting.user_id == request.user_id)
            )
            privacy = result.scalar_one_or_none()

            if privacy is None:
                privacy = PrivacySetting(
                    user_id=request.user_id,
                    who_can_write_me="everyone",
                    who_can_add_to_groups="everyone",
                    who_can_see_phone="everyone",
                    who_can_see_last_seen="everyone",
                )
                session.add(privacy)

            try:
                if request.HasField("who_can_write_me"):
                    privacy.who_can_write_me = self._proto_privacy_to_db(request.who_can_write_me)
                if request.HasField("who_can_add_to_groups"):
                    privacy.who_can_add_to_groups = self._proto_privacy_to_db(request.who_can_add_to_groups)
                if request.HasField("who_can_see_phone"):
                    privacy.who_can_see_phone = self._proto_privacy_to_db(request.who_can_see_phone)
                if request.HasField("who_can_see_last_seen"):
                    privacy.who_can_see_last_seen = self._proto_privacy_to_db(request.who_can_see_last_seen)
            except ValueError as e:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))

            privacy.updated_at = datetime.now(timezone.utc)

            await session.commit()
            await session.refresh(privacy)

            return self._db_privacy_to_proto(privacy)

    def _proto_privacy_to_db(self, proto_level: int) -> str:
        mapping = {
            mess_pb2.PrivacyLevel.EVERYONE: "everyone",
            mess_pb2.PrivacyLevel.CONTACTS: "contacts",
            mess_pb2.PrivacyLevel.NOBODY: "nobody",
        }
        value = mapping.get(proto_level)
        if value is None:
            raise ValueError("Invalid privacy level")
        return value

    def _db_privacy_to_proto(self, db_privacy: PrivacySetting) -> mess_pb2.PrivacySetting:
        def map_to_proto(level_str: str) -> int:
            mapping = {
                "everyone": mess_pb2.PrivacyLevel.EVERYONE,
                "contacts": mess_pb2.PrivacyLevel.CONTACTS,
                "nobody": mess_pb2.PrivacyLevel.NOBODY,
            }
            return mapping.get(level_str, mess_pb2.PrivacyLevel.PRIVACY_LEVEL_UNSPECIFIED)

        ts = Timestamp()
        ts.FromDatetime(db_privacy.updated_at)

        return mess_pb2.PrivacySetting(
            user_id=str(db_privacy.user_id),
            who_can_write_me=map_to_proto(db_privacy.who_can_write_me),
            who_can_add_to_groups=map_to_proto(db_privacy.who_can_add_to_groups),
            who_can_see_phone=map_to_proto(db_privacy.who_can_see_phone),
            who_can_see_last_seen=map_to_proto(db_privacy.who_can_see_last_seen),
            updated_at=ts,
        )