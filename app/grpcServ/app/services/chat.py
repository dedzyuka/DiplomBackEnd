import os
from queue import Empty
import uuid
import datetime
import grpc
from google.protobuf.timestamp_pb2 import Timestamp
import jwt
from sqlalchemy import select, func, update

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

    async def GetChat(self, request: mess_pb2.GetChatRequest, context) -> mess_pb2.Chat:
        """
        Получить полный Chat по chat_id.

        TODO (логика):
        - проверить доступ текущего пользователя к чату
        - загрузить Chat из БД
        - при необходимости подтянуть last_message / last_message_preview
        - вернуть mess_pb2.Chat
        - ошибки:
          * NOT_FOUND, PERMISSION_DENIED, INTERNAL
        """
        # TODO: implement
        raise NotImplementedError()

    async def UpdateChat(self, request: mess_pb2.UpdateChatRequest, context) -> mess_pb2.Chat:
        """
        Обновить настройки чата (name/description/avatar/is_public/max_members).

        TODO (логика):
        - проверить права (OWNER/ADMIN)
        - обновить только те optional поля, которые переданы
        - провалидировать max_members относительно текущего members_count
        - обновить updated_at и/или last_activity_at
        - вернуть обновлённый mess_pb2.Chat
        - ошибки:
          * NOT_FOUND, PERMISSION_DENIED, INVALID_ARGUMENT, INTERNAL
        """
        # TODO: implement
        raise NotImplementedError()

    async def DeleteChat(self, request: mess_pb2.DeleteChatRequest, context) -> Empty:
        """
        Удалить чат (желательно soft-delete).

        TODO (логика):
        - проверить права (обычно OWNER)
        - выполнить soft-delete (или hard-delete, если так задумано)
        - обновить индексы/кэши/счётчики при необходимости
        - вернуть Empty
        - ошибки:
          * NOT_FOUND, PERMISSION_DENIED, INTERNAL
        """
        # TODO: implement
        raise NotImplementedError()

    async def ListChats(self, request: mess_pb2.ListChatsRequest, context) -> mess_pb2.ChatsListResponse:
        """
        Legacy список чатов пользователя (возвращает Chat, может быть тяжёлым).

        TODO (логика):
        - проверить, что request.user_id соответствует текущему пользователю
          (или что у него есть право смотреть этот список)
        - выбрать чаты, где пользователь участник/подписчик
        - применить пагинацию page_size/page_token
        - заполнить ChatsListResponse: chats, next_page_token, total_count
        - ошибки:
          * PERMISSION_DENIED, INVALID_ARGUMENT, INTERNAL
        """
        # TODO: implement
        raise NotImplementedError()

    async def AddChatMember(self, request: mess_pb2.AddChatMemberRequest, context) -> mess_pb2.ChatMember:
        """
        Добавить участника в чат (инвайт/добавление админом).

        TODO (логика):
        - проверить права вызывающего (OWNER/ADMIN) и политики чата
        - провалидировать role (обычно MEMBER)
        - если client_request_id используется: идемпотентность
        - проверить лимиты max_members и статус цели (не забанен ли)
        - создать ChatMember или восстановить (если был LEFT)
        - обновить members_count/last_activity_at
        - вернуть ChatMember
        - ошибки:
          * NOT_FOUND, PERMISSION_DENIED, INVALID_ARGUMENT, RESOURCE_EXHAUSTED, ALREADY_EXISTS, INTERNAL
        """
        # TODO: implement
        raise NotImplementedError()

    async def UpdateChatMember(self, request: mess_pb2.UpdateChatMemberRequest, context) -> mess_pb2.ChatMember:
        """
        Legacy обновление участника (role/status/banned_until).
        (Рекомендуется со временем мигрировать на Kick/Ban/Unban/Leave.)

        TODO (логика):
        - проверить права вызывающего (OWNER/ADMIN)
        - если меняется role: проверить, что нельзя понизить/повысить владельца некорректно
        - если меняется status/banned_until: соблюдать инварианты
          (например BANNED требует banned_until или бессрочный бан)
        - обновить запись ChatMember
        - обновить last_activity_at при необходимости
        - вернуть ChatMember
        - ошибки:
          * NOT_FOUND, PERMISSION_DENIED, INVALID_ARGUMENT, INTERNAL
        """
        # TODO: implement
        raise NotImplementedError()

    async def RemoveChatMember(self, request: mess_pb2.RemoveChatMemberRequest, context) -> Empty:
        """
        Legacy удаление участника.
        Важно: по смыслу может быть либо kick (админ удаляет), либо leave (сам выходит).

        TODO (логика):
        - определить семантику:
          * если request.user_id == current_user_id => leave
          * иначе => kick, требуются права ADMIN/OWNER
        - перевести участника в статус LEFT (soft) и заполнить left_at
        - обновить members_count/last_activity_at
        - вернуть Empty
        - ошибки:
          * NOT_FOUND, PERMISSION_DENIED, INTERNAL
        """
        # TODO: implement
        raise NotImplementedError()

    async def ListChatMembers(self, request: mess_pb2.ListChatMembersRequest, context) -> mess_pb2.ChatMembersListResponse:
        """
        Список участников чата.

        TODO (логика):
        - проверить доступ к чату (участник/права смотреть список)
        - выбрать участников с пагинацией page_size/page_token
        - опционально денормализовать User в поле ChatMember.user
        - вернуть ChatMembersListResponse: members, next_page_token, total_count
        - ошибки:
          * NOT_FOUND, PERMISSION_DENIED, INVALID_ARGUMENT, INTERNAL
        """
        # TODO: implement
        raise NotImplementedError()

    async def ListChatsV2(self, request: mess_pb2.ListChatsRequestV2, context) -> mess_pb2.ChatsListResponseV2:
        """
        Новый лёгкий список для UI/GraphQL: возвращает ChatSummary.

        TODO (логика):
        - проверить права на request.user_id (обычно только сам пользователь)
        - применить фильтры:
          * chat_types
          * archived
          * updated_after
        - применить пагинацию
        - собрать ChatSummary:
          * title/avatar (в т.ч. для PRIVATE вычислить имя собеседника)
          * last_activity_at
          * last_message preview (если include_last_message)
          * counters (если include_counters): unread_count/last_read/mentions
          * my_role, is_muted, is_archived
        - вернуть ChatsListResponseV2
        - ошибки:
          * PERMISSION_DENIED, INVALID_ARGUMENT, INTERNAL
        """
        # TODO: implement
        raise NotImplementedError()

    async def BatchGetChats(self, request: mess_pb2.BatchGetChatsRequest, context) -> mess_pb2.BatchGetChatsResponse:
        """
        Batch получение нескольких чатов для GraphQL (избавляет от N+1).

        TODO (логика):
        - проверить доступ текущего пользователя к каждому chat_id
          (или фильтровать недоступные)
        - собрать ChatSummary по каждому chat_id
        - если include_last_message/include_counters — включить соответствующие части
        - вернуть BatchGetChatsResponse
        - ошибки:
          * INVALID_ARGUMENT, INTERNAL (обычно лучше не падать на один чат)
        """
        # TODO: implement
        raise NotImplementedError()

    async def JoinChat(self, request: mess_pb2.JoinChatRequest, context) -> mess_pb2.ChatMember:
        """
        Явное вступление в чат (по политике join_policy, invite_token).

        TODO (логика):
        - проверить join_policy/visibility:
          * OPEN => можно вступить
          * REQUEST_APPROVAL => создать заявку (если такая модель) или вернуть ошибку/статус
          * INVITE_ONLY => проверить invite_token
        - создать/активировать ChatMember
        - обновить members_count/last_activity_at
        - вернуть ChatMember
        - ошибки:
          * NOT_FOUND, PERMISSION_DENIED, INVALID_ARGUMENT, FAILED_PRECONDITION, INTERNAL
        """
        # TODO: implement
        raise NotImplementedError()

    async def LeaveChat(self, request: mess_pb2.LeaveChatRequest, context) -> Empty:
        """
        Явный выход из чата пользователем.

        TODO (логика):
        - убедиться, что request.user_id == current_user_id (иначе запрет)
        - перевести ChatMember в LEFT, выставить left_at
        - запретить выход единственного OWNER без передачи прав
        - обновить members_count/last_activity_at
        - вернуть Empty
        - ошибки:
          * NOT_FOUND, PERMISSION_DENIED, FAILED_PRECONDITION, INTERNAL
        """
        # TODO: implement
        raise NotImplementedError()

    async def KickMember(self, request: mess_pb2.KickMemberRequest, context) -> Empty:
        """
        Кик участника админом/владельцем.

        TODO (логика):
        - проверить права (ADMIN/OWNER)
        - нельзя кикнуть OWNER (или только owner-ом при передаче прав, зависит от правил)
        - перевести ChatMember в LEFT, выставить left_at, зафиксировать аудит при необходимости
        - обновить members_count/last_activity_at
        - вернуть Empty
        - ошибки:
          * NOT_FOUND, PERMISSION_DENIED, FAILED_PRECONDITION, INTERNAL
        """
        # TODO: implement
        raise NotImplementedError()

    async def BanMember(self, request: mess_pb2.BanMemberRequest, context) -> Empty:
        """
        Бан участника (временно или бессрочно).

        TODO (логика):
        - проверить права (ADMIN/OWNER)
        - выставить статус BANNED, banned_until (или null для бессрочного, как решишь)
        - при необходимости удалить из активных участников (или оставить с banned статусом)
        - обновить members_count/last_activity_at (если считаешь бан как “не участник”)
        - вернуть Empty
        - ошибки:
          * NOT_FOUND, PERMISSION_DENIED, INVALID_ARGUMENT, INTERNAL
        """
        # TODO: implement
        raise NotImplementedError()

    async def UnbanMember(self, request: mess_pb2.UnbanMemberRequest, context) -> Empty:
        """
        Снять бан.

        TODO (логика):
        - проверить права (ADMIN/OWNER)
        - убрать статус BANNED (вернуть ACTIVE_N или восстановить членство по правилам)
        - очистить banned_until
        - вернуть Empty
        - ошибки:
          * NOT_FOUND, PERMISSION_DENIED, FAILED_PRECONDITION, INTERNAL
        """
        # TODO: implement
        raise NotImplementedError()