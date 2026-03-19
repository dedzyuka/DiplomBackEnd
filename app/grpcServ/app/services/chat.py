import os
from google.protobuf.empty_pb2 import Empty
import uuid
import datetime
import grpc
from google.protobuf.timestamp_pb2 import Timestamp
import jwt
from sqlalchemy import select, func, update, delete

from database import AsyncSessionLocal
from protobuf import mess_pb2, mess_pb2_grpc
from services.models import Chat, User, ChatMember
from services.enums import ChatType as DbChatType, MemberRole as DbMemberRole, MemberStatus as DbMemberStatus


def _dt_to_ts(dt: datetime.datetime) -> Timestamp:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


PROTO_CHATTYPE_TO_DB = {
    mess_pb2.PRIVATE: DbChatType.private,
    mess_pb2.GROUP: DbChatType.group,
    mess_pb2.CHANNEL: DbChatType.channel,
}

PROTO_ROLE_TO_DB = {
    mess_pb2.OWNER: DbMemberRole.owner,
    mess_pb2.ADMIN: DbMemberRole.admin,
    mess_pb2.MEMBER: DbMemberRole.member,
}

PROTO_STATUS_TO_DB = {
    mess_pb2.ACTIVE_N: DbMemberStatus.active,
    mess_pb2.LEFT: DbMemberStatus.left,
    mess_pb2.BANNED: DbMemberStatus.banned,
}


class ChatServicer(mess_pb2_grpc.ChatServiceServicer):
    def __init__(self):
        self.secret_key = os.getenv("SECRET_KEY", "change-me-in-production")
        self.algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        self.issuer = os.getenv("JWT_ISSUER", "messenger-backend")
        self.audience = os.getenv("JWT_AUDIENCE", "messenger-clients")

    async def _get_current_user_id(self, context) -> str | None:
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
                    payload = jwt.decode(
                        token,
                        self.secret_key,
                        algorithms=[self.algorithm],
                        audience=self.audience,
                        issuer=self.issuer,
                    )
                    if payload.get("type") == "access":
                        sub = payload.get("sub")
                        if sub:
                            return str(sub)
                except Exception:
                    # Если auth_header невалидный, но есть доверенный x-user-id от API-gateway,
                    # даём fallback вместо немедленного UNAUTHENTICATED.
                    if forwarded_user_id:
                        return forwarded_user_id
                    await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Unauthenticated")

                if forwarded_user_id:
                    return forwarded_user_id
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Unauthenticated")

        if forwarded_user_id:
            return forwarded_user_id

        return None

    async def CreateChat(self, request: mess_pb2.CreateChatRequest, context) -> mess_pb2.Chat:
        # --- auth ---
        creator_id = (
            getattr(context, "current_user_id", None)
            or getattr(context, "user_id", None)
            or await self._get_current_user_id(context)
        )
        if not creator_id:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Unauthenticated")

        try:
            creator_uuid = creator_id if isinstance(creator_id, uuid.UUID) else uuid.UUID(str(creator_id))
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid current_user_id in context")

        # --- validate chat_type ---
        if request.chat_type == mess_pb2.CHAT_TYPE_UNSPECIFIED:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "chat_type is required")

        db_chat_type = PROTO_CHATTYPE_TO_DB.get(request.chat_type)
        if db_chat_type is None:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Unknown chat_type")

        # --- normalize member_ids (-> UUID, dedupe) ---
        raw_member_ids = [m for m in list(request.member_ids) if m]
        raw_member_ids = list(dict.fromkeys(raw_member_ids))  # dedupe preserving order

        member_uuids: list[uuid.UUID] = []
        for mid in raw_member_ids:
            try:
                member_uuids.append(uuid.UUID(str(mid)))
            except Exception:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"Invalid member_id UUID: {mid}")

        # --- enforce per-type rules ---
        other_uuid = None

        if request.chat_type == mess_pb2.PRIVATE:
            others = [u for u in member_uuids if u != creator_uuid]
            if len(others) == 1:
                other_uuid = others[0]
                member_uuids = [creator_uuid, other_uuid]
                max_members = 2
            elif len(others) == 0 and len(member_uuids) == 1 and member_uuids[0] == creator_uuid:
                # Разрешаем self-dialog, если клиент прислал только текущего пользователя.
                other_uuid = None
                member_uuids = [creator_uuid]
                max_members = 1
            else:
                await context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    "PRIVATE chat must have exactly 1 other participant in member_ids",
                )
            is_public = False

        elif request.chat_type == mess_pb2.GROUP:
            if creator_uuid not in member_uuids:
                member_uuids = [creator_uuid] + member_uuids

            is_public = bool(request.is_public)
            max_members = int(request.max_members) if request.HasField("max_members") and request.max_members > 0 else 200

            if len(member_uuids) > max_members:
                await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "max_members exceeded")

        elif request.chat_type == mess_pb2.CHANNEL:
            # допускаем initial admins как member_ids, но creator обязан быть
            if creator_uuid not in member_uuids:
                member_uuids = [creator_uuid] + member_uuids
            else:
                member_uuids = [creator_uuid] + [u for u in member_uuids if u != creator_uuid]

            is_public = bool(request.is_public)
            max_members = int(request.max_members) if request.HasField("max_members") and request.max_members > 0 else 200

            if len(member_uuids) > max_members:
                await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "max_members exceeded")

        else:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Unknown chat_type")

        db_owner_role = PROTO_ROLE_TO_DB[mess_pb2.OWNER]
        db_member_role = PROTO_ROLE_TO_DB[mess_pb2.MEMBER]
        db_active_status = PROTO_STATUS_TO_DB[mess_pb2.ACTIVE_N]

        async with AsyncSessionLocal() as session:
            try:
                if request.chat_type == mess_pb2.PRIVATE:
                    if other_uuid is None:
                        candidate_chat_id_stmt = (
                            select(ChatMember.chat_id)
                            .join(Chat, Chat.chat_id == ChatMember.chat_id)
                            .where(
                                Chat.chat_type == DbChatType.private,
                                ChatMember.user_id == creator_uuid,
                            )
                            .group_by(ChatMember.chat_id)
                            .having(func.count(func.distinct(ChatMember.user_id)) == 1)
                            .having(func.count(ChatMember.user_id) == 1)
                            .limit(1)
                        )
                    else:
                        candidate_chat_id_stmt = (
                            select(ChatMember.chat_id)
                            .join(Chat, Chat.chat_id == ChatMember.chat_id)
                            .where(
                                Chat.chat_type == DbChatType.private,
                                ChatMember.user_id.in_([creator_uuid, other_uuid]),
                            )
                            .group_by(ChatMember.chat_id)
                            .having(func.count(func.distinct(ChatMember.user_id)) == 2)
                            .having(func.count(ChatMember.user_id) == 2)
                            .limit(1)
                            
                        )
                    candidate_chat_id = (await session.execute(candidate_chat_id_stmt)).scalar_one_or_none()

                    if candidate_chat_id is not None:
                        # (опционально) ре-активируем участие создателя/второго, если кто-то выходил
                        await session.execute(
                            update(ChatMember)
                            .where(
                                ChatMember.chat_id == candidate_chat_id,
                                ChatMember.user_id.in_(member_uuids),
                                ChatMember.status == DbMemberStatus.left,
                            )
                            .values(status=DbMemberStatus.active, left_at=None)
                        )
                        await session.commit()

                        existing_chat = (
                            await session.execute(select(Chat).where(Chat.chat_id == candidate_chat_id))
                        ).scalar_one()
                        print(member_uuids)
                        resp = mess_pb2.Chat(
                            chat_id=str(existing_chat.chat_id),
                            chat_type=mess_pb2.PRIVATE,
                            is_public=bool(existing_chat.is_public),
                            max_members=int(existing_chat.max_members),
                            created_at=_dt_to_ts(existing_chat.created_at),

                            members_count=len(member_uuids),
                        )
                        if existing_chat.name is not None:
                            resp.name = existing_chat.name
                        if existing_chat.description is not None:
                            resp.description = existing_chat.description
                        if existing_chat.avatar_url is not None:
                            resp.avatar_url = existing_chat.avatar_url
                        if existing_chat.creator_id is not None:
                            resp.creator_id = str(existing_chat.creator_id)
                        return resp
                # ====== конец анти-дубликата ======

                # validate users exist (для всех типов, включая PRIVATE если не нашли существующий)
                q = select(User.user_id).where(User.user_id.in_(member_uuids))
                found = (await session.execute(q)).scalars().all()
                if len(found) != len(set(member_uuids)):
                    found_set = {str(x) for x in found}
                    missing = [str(u) for u in member_uuids if str(u) not in found_set]
                    await context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"Unknown user_id(s): {missing}")

                new_chat = Chat(
                    chat_type=db_chat_type,
                    name=request.name if request.HasField("name") else None,
                    description=request.description if request.HasField("description") else None,
                    avatar_url=request.avatar_url if request.HasField("avatar_url") else None,
                    creator_id=creator_uuid,
                    is_public=is_public,
                    max_members=max_members,
                )
                session.add(new_chat)
                await session.flush()  # получить new_chat.chat_id

                now = datetime.datetime.now(datetime.timezone.utc)
                for u in member_uuids:
                    session.add(
                        ChatMember(
                            chat_id=new_chat.chat_id,
                            user_id=u,
                            role=db_owner_role if u == creator_uuid else db_member_role,
                            status=db_active_status,
                            joined_at=now,
                        )
                    )

                await session.commit()

                await session.refresh(new_chat)

                resp = mess_pb2.Chat(
                    chat_id=str(new_chat.chat_id),
                    chat_type=request.chat_type,
                    is_public=bool(new_chat.is_public),
                    max_members=int(new_chat.max_members),
                    created_at=_dt_to_ts(new_chat.created_at),
                    members_count=len(member_uuids),
                )
                if new_chat.name is not None:
                    resp.name = new_chat.name
                if new_chat.description is not None:
                    resp.description = new_chat.description
                if new_chat.avatar_url is not None:
                    resp.avatar_url = new_chat.avatar_url
                if new_chat.creator_id is not None:
                    resp.creator_id = str(new_chat.creator_id)

                return resp

            except grpc.RpcError:
                raise
            except Exception as e:
                await session.rollback()
                await context.abort(grpc.StatusCode.INTERNAL, f"CreateChat failed: {e}")

    async def _require_current_user_uuid(self, context) -> uuid.UUID:
        current_user_id = (
            getattr(context, "current_user_id", None)
            or getattr(context, "user_id", None)
            or await self._get_current_user_id(context)
        )
        if not current_user_id:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Unauthenticated")
        try:
            return current_user_id if isinstance(current_user_id, uuid.UUID) else uuid.UUID(str(current_user_id))
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid current_user_id in context")


    @staticmethod
    def _db_role_to_proto(role: DbMemberRole) -> int:
        return {
            DbMemberRole.owner: mess_pb2.OWNER,
            DbMemberRole.admin: mess_pb2.ADMIN,
            DbMemberRole.member: mess_pb2.MEMBER,
        }[role]

    @staticmethod
    def _db_status_to_proto(status: DbMemberStatus) -> int:
        return {
            DbMemberStatus.active: mess_pb2.ACTIVE_N,
            DbMemberStatus.left: mess_pb2.LEFT,
            DbMemberStatus.banned: mess_pb2.BANNED,
        }[status]

    @staticmethod
    def _db_chat_type_to_proto(chat_type: DbChatType) -> int:
        return {
            DbChatType.private: mess_pb2.PRIVATE,
            DbChatType.group: mess_pb2.GROUP,
            DbChatType.channel: mess_pb2.CHANNEL,
        }[chat_type]

    async def _build_chat_proto(self, session, chat: Chat) -> mess_pb2.Chat:
        members_count = (
            await session.execute(
                select(func.count()).select_from(ChatMember).where(
                    ChatMember.chat_id == chat.chat_id,
                    ChatMember.status == DbMemberStatus.active,
                )
            )
        ).scalar_one()

        resp = mess_pb2.Chat(
            chat_id=str(chat.chat_id),
            chat_type=self._db_chat_type_to_proto(chat.chat_type),
            is_public=bool(chat.is_public),
            max_members=int(chat.max_members),
            created_at=_dt_to_ts(chat.created_at),
            members_count=int(members_count),
            updated_at=_dt_to_ts(chat.created_at),
            last_activity_at=_dt_to_ts(chat.created_at),
            visibility=mess_pb2.VISIBILITY_PUBLIC if chat.is_public else mess_pb2.VISIBILITY_PRIVATE,
            join_policy=mess_pb2.JOIN_OPEN if chat.is_public else mess_pb2.JOIN_INVITE_ONLY,
        )
        if chat.name is not None:
            resp.name = chat.name
        if chat.description is not None:
            resp.description = chat.description
        if chat.avatar_url is not None:
            resp.avatar_url = chat.avatar_url
        if chat.creator_id is not None:
            resp.creator_id = str(chat.creator_id)
        return resp

    async def _build_member_proto(self, session, member: ChatMember) -> mess_pb2.ChatMember:
        resp = mess_pb2.ChatMember(
            chat_id=str(member.chat_id),
            user_id=str(member.user_id),
            role=self._db_role_to_proto(member.role),
            status=self._db_status_to_proto(member.status),
            joined_at=_dt_to_ts(member.joined_at),
        )
        if member.left_at:
            resp.left_at.CopyFrom(_dt_to_ts(member.left_at))
        if member.banned_until:
            resp.banned_until.CopyFrom(_dt_to_ts(member.banned_until))

        user = (await session.execute(select(User).where(User.user_id == member.user_id))).scalar_one_or_none()
        if user:
            resp.user.CopyFrom(mess_pb2.User(
                user_id=str(user.user_id),
                nick_name=user.nick_name,
                is_online=bool(user.is_online),
                status=mess_pb2.ACTIVE,
                email_verified=bool(user.email_verified),
                phone_verified=bool(user.phone_verified),
                is_admin=bool(user.is_admin),
                created_at=_dt_to_ts(user.created_at),
                updated_at=_dt_to_ts(user.updated_at),
            ))
        return resp

    async def _get_actor_member(self, session, chat_id: uuid.UUID, user_id: uuid.UUID) -> ChatMember | None:
        return (
            await session.execute(
                select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
            )
        ).scalar_one_or_none()

    async def GetChat(self, request: mess_pb2.GetChatRequest, context) -> mess_pb2.Chat:
        current_user_uuid = await self._require_current_user_uuid(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id")

        async with AsyncSessionLocal() as session:
            chat = (await session.execute(select(Chat).where(Chat.chat_id == chat_uuid))).scalar_one_or_none()
            if not chat:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Chat not found")

            member = await self._get_actor_member(session, chat_uuid, current_user_uuid)
            if not member or member.status != DbMemberStatus.active:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Access denied")
            return await self._build_chat_proto(session, chat)

    async def UpdateChat(self, request: mess_pb2.UpdateChatRequest, context) -> mess_pb2.Chat:
        current_user_uuid = await self._require_current_user_uuid(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id")

        async with AsyncSessionLocal() as session:
            chat = (await session.execute(select(Chat).where(Chat.chat_id == chat_uuid))).scalar_one_or_none()
            if not chat:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Chat not found")

            actor = await self._get_actor_member(session, chat_uuid, current_user_uuid)
            if not actor or actor.status != DbMemberStatus.active or actor.role not in {DbMemberRole.owner, DbMemberRole.admin}:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient permissions")

            if request.HasField("name"):
                chat.name = request.name
            if request.HasField("description"):
                chat.description = request.description
            if request.HasField("avatar_url"):
                chat.avatar_url = request.avatar_url
            if request.HasField("is_public"):
                chat.is_public = request.is_public
            if request.HasField("max_members"):
                if request.max_members <= 0:
                    await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "max_members must be > 0")
                active_count = (await session.execute(select(func.count()).select_from(ChatMember).where(
                    ChatMember.chat_id == chat_uuid, ChatMember.status == DbMemberStatus.active
                ))).scalar_one()
                if request.max_members < active_count:
                    await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "max_members is less than active members")
                chat.max_members = request.max_members

            await session.commit()
            await session.refresh(chat)
            return await self._build_chat_proto(session, chat)

    async def DeleteChat(self, request: mess_pb2.DeleteChatRequest, context) -> Empty:
        current_user_uuid = await self._require_current_user_uuid(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id")

        async with AsyncSessionLocal() as session:
            chat = (await session.execute(select(Chat).where(Chat.chat_id == chat_uuid))).scalar_one_or_none()
            if not chat:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Chat not found")
            actor = await self._get_actor_member(session, chat_uuid, current_user_uuid)
            if not actor or actor.status != DbMemberStatus.active or actor.role != DbMemberRole.owner:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Only owner can delete chat")
            await session.execute(
                delete(ChatMember).where(ChatMember.chat_id == chat_uuid)
            )
            await session.execute(
                delete(Chat).where(Chat.chat_id == chat_uuid)
            )
            await session.commit()
            return Empty()

    async def ListChats(self, request: mess_pb2.ListChatsRequest, context) -> mess_pb2.ChatsListResponse:
        current_user_uuid = await self._require_current_user_uuid(context)
        try:
            requested_user = uuid.UUID(request.user_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid user_id")
        if requested_user != current_user_uuid:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Can list only own chats")

        page_size = request.page_size if request.page_size > 0 else 20
        try:
            offset = int(request.page_token) if request.page_token else 0
        except ValueError:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid page_token")

        async with AsyncSessionLocal() as session:
            total = (await session.execute(select(func.count()).select_from(ChatMember).where(
                ChatMember.user_id == current_user_uuid,
                ChatMember.status == DbMemberStatus.active,
            ))).scalar_one()

            rows = (await session.execute(
                select(Chat)
                .join(ChatMember, ChatMember.chat_id == Chat.chat_id)
                .where(ChatMember.user_id == current_user_uuid, ChatMember.status == DbMemberStatus.active)
                .order_by(Chat.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )).scalars().all()

            chats = [await self._build_chat_proto(session, c) for c in rows]
            next_page = str(offset + page_size) if offset + page_size < total else ""
            return mess_pb2.ChatsListResponse(chats=chats, next_page_token=next_page, total_count=total)

    async def AddChatMember(self, request: mess_pb2.AddChatMemberRequest, context) -> mess_pb2.ChatMember:
        actor_id = await self._require_current_user_uuid(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
            user_uuid = uuid.UUID(request.user_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id/user_id")

        role = PROTO_ROLE_TO_DB.get(request.role, DbMemberRole.member)
        if role == DbMemberRole.owner:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Cannot add member with OWNER role")

        async with AsyncSessionLocal() as session:
            chat = (await session.execute(select(Chat).where(Chat.chat_id == chat_uuid))).scalar_one_or_none()
            if not chat:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Chat not found")

            actor = await self._get_actor_member(session, chat_uuid, actor_id)
            if not actor or actor.status != DbMemberStatus.active or actor.role not in {DbMemberRole.owner, DbMemberRole.admin}:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient permissions")

            user_exists = (await session.execute(select(User.user_id).where(User.user_id == user_uuid))).scalar_one_or_none()
            if not user_exists:
                await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")

            active_count = (await session.execute(select(func.count()).select_from(ChatMember).where(
                ChatMember.chat_id == chat_uuid, ChatMember.status == DbMemberStatus.active
            ))).scalar_one()
            if active_count >= chat.max_members:
                await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "max_members exceeded")

            member = (await session.execute(select(ChatMember).where(
                ChatMember.chat_id == chat_uuid, ChatMember.user_id == user_uuid
            ))).scalar_one_or_none()

            now = datetime.datetime.now(datetime.timezone.utc)
            if member:
                if member.status == DbMemberStatus.active:
                    await context.abort(grpc.StatusCode.ALREADY_EXISTS, "User is already a member")
                if member.status == DbMemberStatus.banned and (member.banned_until is None or member.banned_until > now):
                    await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "User is banned")
                member.status = DbMemberStatus.active
                member.left_at = None
                member.banned_until = None
                member.role = role
                if not member.joined_at:
                    member.joined_at = now
            else:
                member = ChatMember(chat_id=chat_uuid, user_id=user_uuid, role=role, status=DbMemberStatus.active, joined_at=now)
                session.add(member)

            await session.commit()
            await session.refresh(member)
            return await self._build_member_proto(session, member)

    async def UpdateChatMember(self, request: mess_pb2.UpdateChatMemberRequest, context) -> mess_pb2.ChatMember:
        actor_id = await self._require_current_user_uuid(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
            user_uuid = uuid.UUID(request.user_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id/user_id")

        async with AsyncSessionLocal() as session:
            actor = await self._get_actor_member(session, chat_uuid, actor_id)
            if not actor or actor.status != DbMemberStatus.active or actor.role not in {DbMemberRole.owner, DbMemberRole.admin}:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient permissions")

            member = (await session.execute(select(ChatMember).where(
                ChatMember.chat_id == chat_uuid, ChatMember.user_id == user_uuid
            ))).scalar_one_or_none()
            if not member:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Member not found")

            if request.HasField("role"):
                new_role = PROTO_ROLE_TO_DB.get(request.role)
                if not new_role:
                    await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid role")
                if member.role == DbMemberRole.owner and actor.role != DbMemberRole.owner:
                    await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Cannot change owner role")
                if new_role == DbMemberRole.owner and actor.role != DbMemberRole.owner:
                    await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Only owner can assign OWNER")
                member.role = new_role

            if request.HasField("status"):
                new_status = PROTO_STATUS_TO_DB.get(request.status)
                if not new_status:
                    await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid status")
                if member.role == DbMemberRole.owner and new_status != DbMemberStatus.active:
                    await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Cannot change owner status")
                member.status = new_status
                if new_status == DbMemberStatus.left:
                    member.left_at = datetime.datetime.now(datetime.timezone.utc)
                elif new_status == DbMemberStatus.active:
                    member.left_at = None
                    member.banned_until = None

            if request.HasField("banned_until"):
                member.banned_until = request.banned_until.ToDatetime().astimezone(datetime.timezone.utc)

            await session.commit()
            await session.refresh(member)
            return await self._build_member_proto(session, member)

    async def RemoveChatMember(self, request: mess_pb2.RemoveChatMemberRequest, context) -> Empty:
        actor_id = await self._require_current_user_uuid(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
            user_uuid = uuid.UUID(request.user_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id/user_id")

        async with AsyncSessionLocal() as session:
            actor = await self._get_actor_member(session, chat_uuid, actor_id)
            if not actor or actor.status != DbMemberStatus.active:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a chat member")

            is_self_leave = actor_id == user_uuid
            if not is_self_leave and actor.role not in {DbMemberRole.owner, DbMemberRole.admin}:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient permissions")

            member = (await session.execute(select(ChatMember).where(
                ChatMember.chat_id == chat_uuid, ChatMember.user_id == user_uuid
            ))).scalar_one_or_none()
            if not member:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Member not found")
            if member.role == DbMemberRole.owner and not is_self_leave:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Cannot remove OWNER")

            member.status = DbMemberStatus.left
            member.left_at = datetime.datetime.now(datetime.timezone.utc)
            member.banned_until = None
            await session.commit()
            return Empty()

    async def ListChatMembers(self, request: mess_pb2.ListChatMembersRequest, context) -> mess_pb2.ChatMembersListResponse:
        actor_id = await self._require_current_user_uuid(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id")

        page_size = request.page_size if request.page_size > 0 else 50
        try:
            offset = int(request.page_token) if request.page_token else 0
        except ValueError:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid page_token")

        async with AsyncSessionLocal() as session:
            actor = await self._get_actor_member(session, chat_uuid, actor_id)
            if not actor or actor.status != DbMemberStatus.active:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Access denied")

            total = (await session.execute(select(func.count()).select_from(ChatMember).where(ChatMember.chat_id == chat_uuid))).scalar_one()
            rows = (await session.execute(
                select(ChatMember)
                .where(ChatMember.chat_id == chat_uuid)
                .order_by(ChatMember.joined_at.asc())
                .offset(offset)
                .limit(page_size)
            )).scalars().all()
            members = [await self._build_member_proto(session, m) for m in rows]
            next_page = str(offset + page_size) if offset + page_size < total else ""
            return mess_pb2.ChatMembersListResponse(members=members, next_page_token=next_page, total_count=total)

    async def ListChatsV2(self, request: mess_pb2.ListChatsRequestV2, context) -> mess_pb2.ChatsListResponseV2:
        legacy = await self.ListChats(mess_pb2.ListChatsRequest(
            user_id=request.user_id,
            page_size=request.page_size,
            page_token=request.page_token,
        ), context)

        chats = []
        for c in legacy.chats:
            title = c.name if c.HasField("name") else f"Chat {c.chat_id[:8]}"
            summary = mess_pb2.ChatSummary(
                chat_id=c.chat_id,
                chat_type=c.chat_type,
                title=title,
                visibility=mess_pb2.VISIBILITY_PUBLIC if c.is_public else mess_pb2.VISIBILITY_PRIVATE,
                join_policy=mess_pb2.JOIN_OPEN if c.is_public else mess_pb2.JOIN_INVITE_ONLY,
                members_count=c.members_count,
                last_activity_at=c.created_at,
                my_role=mess_pb2.MEMBER,
                is_muted=False,
                is_archived=False,
            )
            if c.HasField("avatar_url"):
                summary.avatar_url = c.avatar_url
            if request.include_counters:
                summary.counters.unread_count = 0
                summary.counters.has_mentions = False
            chats.append(summary)

        return mess_pb2.ChatsListResponseV2(chats=chats, next_page_token=legacy.next_page_token, total_count=legacy.total_count)

    async def BatchGetChats(self, request: mess_pb2.BatchGetChatsRequest, context) -> mess_pb2.BatchGetChatsResponse:
        current_user_uuid = await self._require_current_user_uuid(context)
        chat_ids = []
        for cid in request.chat_ids:
            try:
                chat_ids.append(uuid.UUID(cid))
            except Exception:
                continue

        async with AsyncSessionLocal() as session:
            rows = (await session.execute(
                select(Chat)
                .join(ChatMember, ChatMember.chat_id == Chat.chat_id)
                .where(
                    Chat.chat_id.in_(chat_ids),
                    ChatMember.user_id == current_user_uuid,
                    ChatMember.status == DbMemberStatus.active,
                )
            )).scalars().all()

            chats = []
            for c in rows:
                count = (await session.execute(select(func.count()).select_from(ChatMember).where(
                    ChatMember.chat_id == c.chat_id,
                    ChatMember.status == DbMemberStatus.active,
                ))).scalar_one()
                title = c.name or f"Chat {str(c.chat_id)[:8]}"
                summary = mess_pb2.ChatSummary(
                    chat_id=str(c.chat_id),
                    chat_type=self._db_chat_type_to_proto(c.chat_type),
                    title=title,
                    visibility=mess_pb2.VISIBILITY_PUBLIC if c.is_public else mess_pb2.VISIBILITY_PRIVATE,
                    join_policy=mess_pb2.JOIN_OPEN if c.is_public else mess_pb2.JOIN_INVITE_ONLY,
                    members_count=int(count),
                    last_activity_at=_dt_to_ts(c.created_at),
                    my_role=mess_pb2.MEMBER,
                    is_muted=False,
                    is_archived=False,
                )
                if c.avatar_url:
                    summary.avatar_url = c.avatar_url
                chats.append(summary)
            return mess_pb2.BatchGetChatsResponse(chats=chats)

    async def JoinChat(self, request: mess_pb2.JoinChatRequest, context) -> mess_pb2.ChatMember:
        current_user_uuid = await self._require_current_user_uuid(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
            target_user = uuid.UUID(request.user_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id/user_id")
        if current_user_uuid != target_user:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Can join only as current user")

        async with AsyncSessionLocal() as session:
            chat = (await session.execute(select(Chat).where(Chat.chat_id == chat_uuid))).scalar_one_or_none()
            if not chat:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Chat not found")
            if chat.chat_type == DbChatType.private:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Cannot join PRIVATE chat")

            member = (await session.execute(select(ChatMember).where(
                ChatMember.chat_id == chat_uuid, ChatMember.user_id == target_user
            ))).scalar_one_or_none()

            now = datetime.datetime.now(datetime.timezone.utc)
            if member and member.status == DbMemberStatus.banned and (member.banned_until is None or member.banned_until > now):
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "User is banned")
            if member and member.status == DbMemberStatus.active:
                return await self._build_member_proto(session, member)

            active_count = (await session.execute(select(func.count()).select_from(ChatMember).where(
                ChatMember.chat_id == chat_uuid,
                ChatMember.status == DbMemberStatus.active,
            ))).scalar_one()
            if active_count >= chat.max_members:
                await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "max_members exceeded")

            if member:
                member.status = DbMemberStatus.active
                member.left_at = None
                member.banned_until = None
            else:
                member = ChatMember(chat_id=chat_uuid, user_id=target_user, role=DbMemberRole.member, status=DbMemberStatus.active, joined_at=now)
                session.add(member)

            await session.commit()
            await session.refresh(member)
            return await self._build_member_proto(session, member)

    async def LeaveChat(self, request: mess_pb2.LeaveChatRequest, context) -> Empty:
        current_user_uuid = await self._require_current_user_uuid(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
            target_user = uuid.UUID(request.user_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id/user_id")
        if current_user_uuid != target_user:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Can leave only own membership")

        async with AsyncSessionLocal() as session:
            member = (await session.execute(select(ChatMember).where(
                ChatMember.chat_id == chat_uuid, ChatMember.user_id == target_user
            ))).scalar_one_or_none()
            if not member:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Member not found")
            if member.status != DbMemberStatus.active:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Member is not active")

            if member.role == DbMemberRole.owner:
                owners = (await session.execute(select(func.count()).select_from(ChatMember).where(
                    ChatMember.chat_id == chat_uuid,
                    ChatMember.status == DbMemberStatus.active,
                    ChatMember.role == DbMemberRole.owner,
                ))).scalar_one()
                if owners <= 1:
                    await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Transfer owner role before leaving")

            member.status = DbMemberStatus.left
            member.left_at = datetime.datetime.now(datetime.timezone.utc)
            await session.commit()
            return Empty()

    async def KickMember(self, request: mess_pb2.KickMemberRequest, context) -> Empty:
        current_user_uuid = await self._require_current_user_uuid(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
            target_user = uuid.UUID(request.user_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id/user_id")

        async with AsyncSessionLocal() as session:
            actor = await self._get_actor_member(session, chat_uuid, current_user_uuid)
            if not actor or actor.status != DbMemberStatus.active or actor.role not in {DbMemberRole.owner, DbMemberRole.admin}:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient permissions")

            member = (await session.execute(select(ChatMember).where(
                ChatMember.chat_id == chat_uuid, ChatMember.user_id == target_user
            ))).scalar_one_or_none()
            if not member:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Member not found")
            if member.role == DbMemberRole.owner:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Cannot kick owner")

            member.status = DbMemberStatus.left
            member.left_at = datetime.datetime.now(datetime.timezone.utc)
            await session.commit()
            return Empty()

    async def BanMember(self, request: mess_pb2.BanMemberRequest, context) -> Empty:
        current_user_uuid = await self._require_current_user_uuid(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
            target_user = uuid.UUID(request.user_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id/user_id")

        async with AsyncSessionLocal() as session:
            actor = await self._get_actor_member(session, chat_uuid, current_user_uuid)
            if not actor or actor.status != DbMemberStatus.active or actor.role not in {DbMemberRole.owner, DbMemberRole.admin}:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient permissions")

            member = (await session.execute(select(ChatMember).where(
                ChatMember.chat_id == chat_uuid, ChatMember.user_id == target_user
            ))).scalar_one_or_none()
            if not member:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Member not found")
            if member.role == DbMemberRole.owner:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Cannot ban owner")

            banned_until = None
            if request.HasField("banned_until"):
                banned_until = request.banned_until.ToDatetime().astimezone(datetime.timezone.utc)
                if banned_until <= datetime.datetime.now(datetime.timezone.utc):
                    await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "banned_until must be in the future")

            member.status = DbMemberStatus.banned
            member.banned_until = banned_until
            member.left_at = datetime.datetime.now(datetime.timezone.utc)
            await session.commit()
            return Empty()

    async def UnbanMember(self, request: mess_pb2.UnbanMemberRequest, context) -> Empty:
        current_user_uuid = await self._require_current_user_uuid(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
            target_user = uuid.UUID(request.user_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id/user_id")

        async with AsyncSessionLocal() as session:
            actor = await self._get_actor_member(session, chat_uuid, current_user_uuid)
            if not actor or actor.status != DbMemberStatus.active or actor.role not in {DbMemberRole.owner, DbMemberRole.admin}:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient permissions")

            member = (await session.execute(select(ChatMember).where(
                ChatMember.chat_id == chat_uuid, ChatMember.user_id == target_user
            ))).scalar_one_or_none()
            if not member:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Member not found")
            if member.status != DbMemberStatus.banned:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Member is not banned")

            member.status = DbMemberStatus.active
            member.banned_until = None
            member.left_at = None
            await session.commit()
            return Empty()