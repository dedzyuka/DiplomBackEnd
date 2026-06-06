from typing import Optional
import uuid
from datetime import datetime, timezone, timedelta
import grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy import delete, select, func, update, desc
from sqlalchemy.orm import selectinload

from services.redis_client import redis_client
from database import AsyncSessionLocal
from protobuf import mess_pb2, mess_pb2_grpc
from services.access_session import require_current_user_uuid
from services.models import Chat, User, ChatMember, Message, Attachment
from services.enums import (
    ChatType as DbChatType,
    MemberRole as DbMemberRole,
    MemberStatus as DbMemberStatus,
)


def _dt_to_ts(dt: datetime) -> Timestamp:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
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

DB_MESSAGE_TYPE_TO_PROTO = {
    "text": mess_pb2.TEXT,
    "image": mess_pb2.IMAGE,
    "video": mess_pb2.VIDEO,
    "audio": mess_pb2.AUDIO,
    "file": mess_pb2.FILE,
    "voice": mess_pb2.VOICE,
    "sticker": mess_pb2.STICKER,
    "location": mess_pb2.LOCATION,
    "contact": mess_pb2.CONTACT,
    "system": mess_pb2.SYSTEM,
}


class ChatServicer(mess_pb2_grpc.ChatServiceServicer):
    async def _require_current_user_uuid(self, context) -> uuid.UUID:
        return await require_current_user_uuid(context)

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

    async def _build_chat_proto(self, session, chat: Chat, current_user_id: Optional[uuid.UUID] = None) -> mess_pb2.Chat:
        members_count = (
            await session.execute(
                select(func.count()).select_from(ChatMember).where(
                    ChatMember.chat_id == chat.chat_id,
                    ChatMember.status == DbMemberStatus.active,
                )
            )
        ).scalar_one()

        if chat.is_public:
            join_policy = mess_pb2.JOIN_OPEN
        else:
            join_policy = mess_pb2.JOIN_INVITE_ONLY

        resp = mess_pb2.Chat(
            chat_id=str(chat.chat_id),
            chat_type=self._db_chat_type_to_proto(chat.chat_type),
            is_public=bool(chat.is_public),
            max_members=int(chat.max_members),
            created_at=_dt_to_ts(chat.created_at),
            members_count=int(members_count),
            updated_at=_dt_to_ts(chat.updated_at or chat.created_at),
            last_activity_at=_dt_to_ts(chat.updated_at or chat.created_at),
            visibility=mess_pb2.VISIBILITY_PUBLIC if chat.is_public else mess_pb2.VISIBILITY_PRIVATE,
            join_policy=join_policy,
        )

        if chat.name is not None:
            resp.name = chat.name
        if chat.description is not None:
            resp.description = chat.description
        if chat.avatar_url is not None:
            resp.avatar_url = chat.avatar_url
        if chat.creator_id is not None:
            resp.creator_id = str(chat.creator_id)

        if current_user_id:
            actor = await self._get_actor_member(session, chat.chat_id, current_user_id)
            if actor:
                resp.my_role = self._db_role_to_proto(actor.role)
            else:
                resp.my_role = mess_pb2.MEMBER_ROLE_UNSPECIFIED
        else:
            resp.my_role = mess_pb2.MEMBER_ROLE_UNSPECIFIED

        if current_user_id:
            preview = await self._get_last_message_preview(session, chat.chat_id)
            if preview:
                resp.last_message_preview.CopyFrom(preview)

        return resp

    async def _get_last_message_preview(self, session, chat_id: uuid.UUID) -> Optional[mess_pb2.MessagePreview]:
        stmt = (
            select(Message)
            .where(Message.chat_id == chat_id, Message.deleted_at.is_(None))
            .order_by(desc(Message.created_at))
            .limit(1)
        )
        last_msg = (await session.execute(stmt)).scalar_one_or_none()
        if not last_msg:
            return None

        text_preview = None
        if last_msg.content and last_msg.content.strip():
            text_preview = last_msg.content
        else:
            att_stmt = select(Attachment).where(Attachment.message_id == last_msg.message_id)
            attachments = (await session.execute(att_stmt)).scalars().all()
            if attachments:
                first = attachments[0]
                if first.mime_type:
                    if first.mime_type.startswith('image/'):
                        text_preview = "📷 Изображение"
                    elif first.mime_type.startswith('video/'):
                        text_preview = "🎥 Видео"
                    elif first.mime_type.startswith('audio/'):
                        text_preview = "🎵 Аудио"
                    else:
                        text_preview = "📎 Файл"
                else:
                    text_preview = "Вложение"
            else:
                text_preview = ""

        msg_type_enum = DB_MESSAGE_TYPE_TO_PROTO.get(last_msg.type, mess_pb2.TEXT)

        preview = mess_pb2.MessagePreview(
            message_id=last_msg.message_id,
            sender_id=str(last_msg.sender_id),
            type=msg_type_enum,
            created_at=_dt_to_ts(last_msg.created_at),
            is_deleted=False,
        )
        if text_preview:
            preview.text_preview = text_preview
        return preview

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

        user = (
            await session.execute(select(User).where(User.user_id == member.user_id))
        ).scalar_one_or_none()
        if user:
            resp.user.CopyFrom(
                mess_pb2.User(
                    user_id=str(user.user_id),
                    nick_name=user.nick_name,
                    is_online=bool(user.is_online),
                    status=mess_pb2.ACTIVE,
                    email_verified=bool(user.email_verified),
                    phone_verified=bool(user.phone_verified),
                    is_admin=bool(user.is_admin),
                    created_at=_dt_to_ts(user.created_at),
                    updated_at=_dt_to_ts(user.updated_at),
                )
            )
        return resp

    async def _get_actor_member(self, session, chat_id: uuid.UUID, user_id: uuid.UUID) -> ChatMember | None:
        return (
            await session.execute(
                select(ChatMember).where(
                    ChatMember.chat_id == chat_id,
                    ChatMember.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def CreateChat(self, request: mess_pb2.CreateChatRequest, context) -> mess_pb2.Chat:
        creator_uuid = await self._require_current_user_uuid(context)

        if request.chat_type == mess_pb2.CHAT_TYPE_UNSPECIFIED:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "chat_type is required")

        db_chat_type = PROTO_CHATTYPE_TO_DB.get(request.chat_type)
        if db_chat_type is None:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Unknown chat_type")

        raw_member_ids = [m for m in list(request.member_ids) if m]
        raw_member_ids = list(dict.fromkeys(raw_member_ids))

        member_uuids: list[uuid.UUID] = []
        for mid in raw_member_ids:
            try:
                member_uuids.append(uuid.UUID(str(mid)))
            except Exception:
                await context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    f"Invalid member_id UUID: {mid}",
                )

        other_uuid = None

        if request.chat_type == mess_pb2.PRIVATE:
            others = [u for u in member_uuids if u != creator_uuid]
            if len(others) == 1:
                other_uuid = others[0]
                member_uuids = [creator_uuid, other_uuid]
                max_members = 2
            elif len(others) == 0 and len(member_uuids) == 1 and member_uuids[0] == creator_uuid:
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
            max_members = (
                int(request.max_members)
                if request.HasField("max_members") and request.max_members > 0
                else 200
            )

            if len(member_uuids) > max_members:
                await context.abort(
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    "max_members exceeded",
                )

        elif request.chat_type == mess_pb2.CHANNEL:
            if creator_uuid not in member_uuids:
                member_uuids = [creator_uuid] + member_uuids
            else:
                member_uuids = [creator_uuid] + [u for u in member_uuids if u != creator_uuid]

            is_public = bool(request.is_public)
            max_members = (
                int(request.max_members)
                if request.HasField("max_members") and request.max_members > 0
                else 200
            )

            if len(member_uuids) > max_members:
                await context.abort(
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    "max_members exceeded",
                )

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

                    candidate_chat_id = (
                        await session.execute(candidate_chat_id_stmt)
                    ).scalar_one_or_none()

                    if candidate_chat_id is not None:
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
                            await session.execute(
                                select(Chat).where(Chat.chat_id == candidate_chat_id)
                            )
                        ).scalar_one()

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

                q = select(User.user_id).where(User.user_id.in_(member_uuids))
                found = (await session.execute(q)).scalars().all()
                if len(found) != len(set(member_uuids)):
                    found_set = {str(x) for x in found}
                    missing = [str(u) for u in member_uuids if str(u) not in found_set]
                    await context.abort(
                        grpc.StatusCode.INVALID_ARGUMENT,
                        f"Unknown user_id(s): {missing}",
                    )

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
                await session.flush()

                now = datetime.now(timezone.utc)
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

    async def GetChat(self, request: mess_pb2.GetChatRequest, context) -> mess_pb2.Chat:
        current_user_uuid = await self._require_current_user_uuid(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id")

        async with AsyncSessionLocal() as session:
            chat = (
                await session.execute(select(Chat).where(Chat.chat_id == chat_uuid))
            ).scalar_one_or_none()
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
            chat = (
                await session.execute(select(Chat).where(Chat.chat_id == chat_uuid))
            ).scalar_one_or_none()
            if not chat:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Chat not found")

            actor = await self._get_actor_member(session, chat_uuid, current_user_uuid)
            if (
                not actor
                or actor.status != DbMemberStatus.active
                or actor.role not in {DbMemberRole.owner, DbMemberRole.admin}
            ):
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
                active_count = (
                    await session.execute(
                        select(func.count()).select_from(ChatMember).where(
                            ChatMember.chat_id == chat_uuid,
                            ChatMember.status == DbMemberStatus.active,
                        )
                    )
                ).scalar_one()
                if request.max_members < active_count:
                    await context.abort(
                        grpc.StatusCode.INVALID_ARGUMENT,
                        "max_members is less than active members",
                    )
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
            chat = (
                await session.execute(select(Chat).where(Chat.chat_id == chat_uuid))
            ).scalar_one_or_none()
            if not chat:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Chat not found")

            actor = await self._get_actor_member(session, chat_uuid, current_user_uuid)
            if (
                not actor
                or actor.status != DbMemberStatus.active
                or actor.role != DbMemberRole.owner
            ):
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Only owner can delete chat")

            await session.execute(delete(ChatMember).where(ChatMember.chat_id == chat_uuid))
            await session.execute(delete(Chat).where(Chat.chat_id == chat_uuid))
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
            total = (
                await session.execute(
                    select(func.count()).select_from(ChatMember).where(
                        ChatMember.user_id == current_user_uuid,
                        ChatMember.status == DbMemberStatus.active,
                    )
                )
            ).scalar_one()

            rows = (
                await session.execute(
                    select(Chat)
                    .join(ChatMember, ChatMember.chat_id == Chat.chat_id)
                    .where(
                        ChatMember.user_id == current_user_uuid,
                        ChatMember.status == DbMemberStatus.active,
                    )
                    .order_by(Chat.updated_at.desc(), Chat.created_at.desc())
                    .offset(offset)
                    .limit(page_size)
                )
            ).scalars().all()

            chats = [await self._build_chat_proto(session, c, current_user_uuid) for c in rows]

            next_page = str(offset + page_size) if offset + page_size < total else ""
            return mess_pb2.ChatsListResponse(
                chats=chats,
                next_page_token=next_page,
                total_count=total,
            )

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
            chat = (
                await session.execute(select(Chat).where(Chat.chat_id == chat_uuid))
            ).scalar_one_or_none()
            if not chat:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Chat not found")

            actor = await self._get_actor_member(session, chat_uuid, actor_id)
            if (
                not actor
                or actor.status != DbMemberStatus.active
                or actor.role not in {DbMemberRole.owner, DbMemberRole.admin}
            ):
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient permissions")

            user_exists = (
                await session.execute(select(User.user_id).where(User.user_id == user_uuid))
            ).scalar_one_or_none()
            if not user_exists:
                await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")

            active_count = (
                await session.execute(
                    select(func.count()).select_from(ChatMember).where(
                        ChatMember.chat_id == chat_uuid,
                        ChatMember.status == DbMemberStatus.active,
                    )
                )
            ).scalar_one()
            if active_count >= chat.max_members:
                await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "max_members exceeded")

            member = (
                await session.execute(
                    select(ChatMember).where(
                        ChatMember.chat_id == chat_uuid,
                        ChatMember.user_id == user_uuid,
                    )
                )
            ).scalar_one_or_none()

            now = datetime.now(timezone.utc)
            if member:
                if member.status == DbMemberStatus.active:
                    await context.abort(grpc.StatusCode.ALREADY_EXISTS, "User is already a member")
                if (
                    member.status == DbMemberStatus.banned
                    and (member.banned_until is None or member.banned_until > now)
                ):
                    await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "User is banned")
                member.status = DbMemberStatus.active
                member.left_at = None
                member.banned_until = None
                member.role = role
                if not member.joined_at:
                    member.joined_at = now
            else:
                member = ChatMember(
                    chat_id=chat_uuid,
                    user_id=user_uuid,
                    role=role,
                    status=DbMemberStatus.active,
                    joined_at=now,
                )
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
            if (
                not actor
                or actor.status != DbMemberStatus.active
                or actor.role not in {DbMemberRole.owner, DbMemberRole.admin}
            ):
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient permissions")

            member = (
                await session.execute(
                    select(ChatMember).where(
                        ChatMember.chat_id == chat_uuid,
                        ChatMember.user_id == user_uuid,
                    )
                )
            ).scalar_one_or_none()
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
                    member.left_at = datetime.now(timezone.utc)
                elif new_status == DbMemberStatus.active:
                    member.left_at = None
                    member.banned_until = None

            if request.HasField("banned_until"):
                member.banned_until = request.banned_until.ToDatetime().astimezone(timezone.utc)

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

            member = (
                await session.execute(
                    select(ChatMember).where(
                        ChatMember.chat_id == chat_uuid,
                        ChatMember.user_id == user_uuid,
                    )
                )
            ).scalar_one_or_none()
            if not member:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Member not found")
            if member.role == DbMemberRole.owner and not is_self_leave:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Cannot remove OWNER")

            member.status = DbMemberStatus.left
            member.left_at = datetime.now(timezone.utc)
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

            total = (
                await session.execute(
                    select(func.count()).select_from(ChatMember).where(
                        ChatMember.chat_id == chat_uuid
                    )
                )
            ).scalar_one()
            rows = (
                await session.execute(
                    select(ChatMember)
                    .where(ChatMember.chat_id == chat_uuid)
                    .order_by(ChatMember.joined_at.asc())
                    .offset(offset)
                    .limit(page_size)
                )
            ).scalars().all()

            members = [await self._build_member_proto(session, m) for m in rows]
            next_page = str(offset + page_size) if offset + page_size < total else ""
            return mess_pb2.ChatMembersListResponse(
                members=members,
                next_page_token=next_page,
                total_count=total,
            )

    async def JoinChat(self, request: mess_pb2.JoinChatRequest, context) -> mess_pb2.ChatMember:
        current_user_uuid = await self._require_current_user_uuid(context)

        chat_uuid = None
        target_user_uuid = current_user_uuid

        if request.HasField("invite_token") and request.invite_token.strip():
            invite_token = request.invite_token.strip()
            chat_id_from_invite = await redis_client.get_invite_chat_id(invite_token)
            if not chat_id_from_invite:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Invalid or expired invite token")
            chat_uuid = uuid.UUID(chat_id_from_invite)
            if request.user_id and request.user_id.strip():
                requested_user = uuid.UUID(request.user_id)
                if requested_user != current_user_uuid:
                    await context.abort(grpc.StatusCode.PERMISSION_DENIED, "User mismatch")
        else:
            try:
                chat_uuid = uuid.UUID(request.chat_id)
                target_user_uuid = uuid.UUID(request.user_id)
            except Exception:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id/user_id")

            if current_user_uuid != target_user_uuid:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Can join only as current user")

        if not chat_uuid:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Chat identifier missing")

        async with AsyncSessionLocal() as session:
            chat = (await session.execute(select(Chat).where(Chat.chat_id == chat_uuid))).scalar_one_or_none()
            if not chat:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Chat not found")
            if chat.chat_type == DbChatType.private:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Cannot join PRIVATE chat")

            member = (await session.execute(
                select(ChatMember).where(
                    ChatMember.chat_id == chat_uuid,
                    ChatMember.user_id == target_user_uuid,
                )
            )).scalar_one_or_none()

            now = datetime.now(timezone.utc)
            if member and member.status == DbMemberStatus.banned and (member.banned_until is None or member.banned_until > now):
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "User is banned")
            if member and member.status == DbMemberStatus.active:
                return await self._build_member_proto(session, member)

            active_count = (await session.execute(
                select(func.count()).select_from(ChatMember).where(
                    ChatMember.chat_id == chat_uuid,
                    ChatMember.status == DbMemberStatus.active,
                )
            )).scalar_one()
            if active_count >= chat.max_members:
                await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "max_members exceeded")

            if member:
                member.status = DbMemberStatus.active
                member.left_at = None
                member.banned_until = None
            else:
                member = ChatMember(
                    chat_id=chat_uuid,
                    user_id=target_user_uuid,
                    role=DbMemberRole.member,
                    status=DbMemberStatus.active,
                    joined_at=now,
                )
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
            member = (
                await session.execute(
                    select(ChatMember).where(
                        ChatMember.chat_id == chat_uuid,
                        ChatMember.user_id == target_user,
                    )
                )
            ).scalar_one_or_none()
            if not member:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Member not found")
            if member.status != DbMemberStatus.active:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Member is not active")

            if member.role == DbMemberRole.owner:
                owners = (
                    await session.execute(
                        select(func.count()).select_from(ChatMember).where(
                            ChatMember.chat_id == chat_uuid,
                            ChatMember.status == DbMemberStatus.active,
                            ChatMember.role == DbMemberRole.owner,
                        )
                    )
                ).scalar_one()
                if owners <= 1:
                    await context.abort(
                        grpc.StatusCode.FAILED_PRECONDITION,
                        "Transfer owner role before leaving",
                    )

            member.status = DbMemberStatus.left
            member.left_at = datetime.now(timezone.utc)
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
            if (
                not actor
                or actor.status != DbMemberStatus.active
                or actor.role not in {DbMemberRole.owner, DbMemberRole.admin}
            ):
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient permissions")

            member = (
                await session.execute(
                    select(ChatMember).where(
                        ChatMember.chat_id == chat_uuid,
                        ChatMember.user_id == target_user,
                    )
                )
            ).scalar_one_or_none()
            if not member:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Member not found")
            if member.role == DbMemberRole.owner:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Cannot kick owner")

            member.status = DbMemberStatus.left
            member.left_at = datetime.now(timezone.utc)
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
            if (
                not actor
                or actor.status != DbMemberStatus.active
                or actor.role not in {DbMemberRole.owner, DbMemberRole.admin}
            ):
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient permissions")

            member = (
                await session.execute(
                    select(ChatMember).where(
                        ChatMember.chat_id == chat_uuid,
                        ChatMember.user_id == target_user,
                    )
                )
            ).scalar_one_or_none()
            if not member:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Member not found")
            if member.role == DbMemberRole.owner:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Cannot ban owner")

            banned_until = None
            if request.HasField("banned_until"):
                banned_until = request.banned_until.ToDatetime().astimezone(timezone.utc)
                if banned_until <= datetime.now(timezone.utc):
                    await context.abort(
                        grpc.StatusCode.INVALID_ARGUMENT,
                        "banned_until must be in the future",
                    )

            member.status = DbMemberStatus.banned
            member.banned_until = banned_until
            member.left_at = datetime.now(timezone.utc)
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
            if (
                not actor
                or actor.status != DbMemberStatus.active
                or actor.role not in {DbMemberRole.owner, DbMemberRole.admin}
            ):
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient permissions")

            member = (
                await session.execute(
                    select(ChatMember).where(
                        ChatMember.chat_id == chat_uuid,
                        ChatMember.user_id == target_user,
                    )
                )
            ).scalar_one_or_none()
            if not member:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Member not found")
            if member.status != DbMemberStatus.banned:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Member is not banned")

            member.status = DbMemberStatus.active
            member.banned_until = None
            member.left_at = None
            await session.commit()
            return Empty()

    async def GenerateInviteLink(self, request: mess_pb2.GenerateInviteLinkRequest, context):
        current_user_uuid = await self._require_current_user_uuid(context)
        chat_uuid = uuid.UUID(request.chat_id)

        async with AsyncSessionLocal() as session:
            actor = await self._get_actor_member(session, chat_uuid, current_user_uuid)
            if not actor or actor.status != DbMemberStatus.active:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a member")

            chat = (await session.execute(select(Chat).where(Chat.chat_id == chat_uuid))).scalar_one()
            if chat.chat_type != DbChatType.private:
                if actor.role not in (DbMemberRole.owner, DbMemberRole.admin):
                    await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Only owner or admin can generate invite link")

            token = str(uuid.uuid4())
            ttl = 60 * 60 * 24
            await redis_client.set_invite_token(token, str(chat_uuid), ttl)

            expire_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
            resp = mess_pb2.InviteLink(invite_key=token)
            resp.expire_at.FromDatetime(expire_at)
            return resp