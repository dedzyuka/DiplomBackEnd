import datetime
import uuid

import grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy import select, func, and_

from database import AsyncSessionLocal
from protobuf import mess_pb2, mess_pb2_grpc
from services.access_session import require_current_user_uuid
from services.enums import MessageType as DbMessageType
from services.models import Message, Chat, ChatMember, MessageStatus, User
from services.enums import MemberRole as MemberRole, MemberStatus


def _dt_to_ts(dt: datetime.datetime) -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


class MessageServicer(mess_pb2_grpc.MessageServiceServicer):
    async def _require_current_user(self, context) -> uuid.UUID:
        return await require_current_user_uuid(context)

    async def SendMessage(self, request: mess_pb2.SendMessageRequest, context):
        sender_uuid = await self._require_current_user(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id")

        # Проверка членства отправителя
        async with AsyncSessionLocal() as session:
            member = (
                await session.execute(
                    select(ChatMember).where(
                        ChatMember.chat_id == chat_uuid,
                        ChatMember.user_id == sender_uuid,
                        ChatMember.status == MemberStatus.active,
                    )
                )
            ).scalar_one_or_none()

            if not member:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a member of this chat")

            # Создаём сообщение
            now = datetime.datetime.now(datetime.timezone.utc)
            msg = Message(
                chat_id=chat_uuid,
                sender_id=sender_uuid,
                content=request.content if request.HasField("content") else None,
                type=DbMessageType.text if request.type == mess_pb2.TEXT else DbMessageType.text,
                # можно добавить маппинг для других типов
                message_metadata=dict(request.message_metadata) if request.HasField("message_metadata") else None,
                reply_to_id=request.reply_to_id if request.HasField("reply_to_id") else None,
                created_at=now,
                updated_at=now,
            )
            session.add(msg)
            await session.flush()  # чтобы получить message_id

            # Статусы доставки для всех активных участников чата
            member_ids = (
                await session.execute(
                    select(ChatMember.user_id).where(
                        ChatMember.chat_id == chat_uuid,
                        ChatMember.status == MemberStatus.active,
                    )
                )
            ).scalars().all()

            for uid in member_ids:
                if uid != sender_uuid:   # отправителю статус не нужен
                    session.add(MessageStatus(
                        message_id=msg.message_id,
                        user_id=uid,
                        message_created_at=msg.created_at,
                        delivered_at=None,
                        read_at=None,
                    ))

            await session.commit()
            await session.refresh(msg)

            # Формируем protobuf-ответ
            result = mess_pb2.Message(
                message_id=msg.message_id,
                chat_id=str(msg.chat_id),
                sender_id=str(msg.sender_id),
                type=request.type,
                created_at=_dt_to_ts(msg.created_at),
                updated_at=_dt_to_ts(msg.updated_at),
                is_edited=False,
            )
            if msg.content:
                result.content = msg.content
            if msg.reply_to_id:
                result.reply_to_id = msg.reply_to_id
            return result

    async def GetMessage(self, request: mess_pb2.GetMessageRequest, context):
        _ = await self._require_current_user(context)  # авторизация
        try:
            chat_uuid = uuid.UUID(request.chat_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id")

        async with AsyncSessionLocal() as session:
            msg = (
                await session.execute(
                    select(Message).where(
                        Message.message_id == request.message_id,
                        Message.chat_id == chat_uuid,
                        Message.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()

            if not msg:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Message not found")

            # Собираем статусы доставки/прочтения для этого сообщения
            statuses = (
                await session.execute(
                    select(MessageStatus).where(MessageStatus.message_id == msg.message_id)
                )
            ).scalars().all()

            return self._message_to_proto(msg, statuses)

    async def ListMessages(self, request: mess_pb2.ListMessagesRequest, context):
        _ = await self._require_current_user(context)
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
            # Проверяем членство (опционально, но желательно)
            # ...

            # Запрос сообщений
            stmt = (
                select(Message)
                .where(
                    Message.chat_id == chat_uuid,
                    Message.deleted_at.is_(None),
                )
                .order_by(Message.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            messages = (await session.execute(stmt)).scalars().all()

            # Для каждого сообщения подгрузим статусы (можно оптимизировать одним запросом)
            proto_messages = []
            for msg in messages:
                statuses = (
                    await session.execute(
                        select(MessageStatus).where(MessageStatus.message_id == msg.message_id)
                    )
                ).scalars().all()
                proto_messages.append(self._message_to_proto(msg, statuses))

            total = (
                await session.execute(
                    select(func.count(Message.message_id)).where(
                        Message.chat_id == chat_uuid,
                        Message.deleted_at.is_(None),
                    )
                )
            ).scalar_one()

            next_page = str(offset + page_size) if offset + page_size < total else ""
            return mess_pb2.MessagesListResponse(
                messages=proto_messages,
                next_page_token=next_page,
                total_count=total,
            )

    async def UpdateMessage(self, request: mess_pb2.UpdateMessageRequest, context):
        user_uuid = await self._require_current_user(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id")

        async with AsyncSessionLocal() as session:
            msg = (
                await session.execute(
                    select(Message).where(
                        Message.message_id == request.message_id,
                        Message.chat_id == chat_uuid,
                        Message.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()

            if not msg:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Message not found")
            if msg.sender_id != user_uuid:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Only sender can edit the message")

            if request.HasField("content"):
                msg.content = request.content
            # ecrypted_content, metadata по желанию
            msg.updated_at = datetime.datetime.now(datetime.timezone.utc)
            msg.is_edited = True

            await session.commit()
            await session.refresh(msg)

            return self._message_to_proto(msg)  # без статусов

    async def DeleteMessage(self, request: mess_pb2.DeleteMessageRequest, context):
        user_uuid = await self._require_current_user(context)
        try:
            chat_uuid = uuid.UUID(request.chat_id)
        except Exception:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid chat_id")

        async with AsyncSessionLocal() as session:
            msg = (
                await session.execute(
                    select(Message).where(
                        Message.message_id == request.message_id,
                        Message.chat_id == chat_uuid,
                    )
                )
            ).scalar_one_or_none()

            if not msg:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Message not found")

            # Право на удаление: автор или admin/owner чата
            if msg.sender_id != user_uuid:
                member = await session.execute(
                    select(ChatMember).where(
                        ChatMember.chat_id == chat_uuid,
                        ChatMember.user_id == user_uuid,
                        ChatMember.status == MemberStatus.active,
                    )
                ).scalar_one_or_none()
                if not member or member.role not in (MemberRole.admin, MemberRole.owner):
                    await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Insufficient permissions")

            msg.deleted_at = datetime.datetime.now(datetime.timezone.utc)
            await session.commit()

        return Empty()

    async def GetMessageStatus(self, request, context):
        # Можно реализовать позже, возвращая список MessageStatus
        pass

    def _message_to_proto(self, msg: Message, statuses: list[MessageStatus] | None = None) -> mess_pb2.Message:
        pb = mess_pb2.Message(
            message_id=msg.message_id,
            chat_id=str(msg.chat_id),
            sender_id=str(msg.sender_id),
            type=mess_pb2.TEXT,  # упростим
            created_at=_dt_to_ts(msg.created_at),
            updated_at=_dt_to_ts(msg.updated_at),
            is_edited=msg.is_edited,
        )
        if msg.content:
            pb.content = msg.content
        if msg.reply_to_id:
            pb.reply_to_id = msg.reply_to_id
        if msg.deleted_at:
            pb.deleted_at.CopyFrom(_dt_to_ts(msg.deleted_at))

        if statuses:
            pb.statuses.extend([
                mess_pb2.MessageStatus(
                    message_id=s.message_id,
                    user_id=str(s.user_id),
                    message_created_at=_dt_to_ts(s.message_created_at),
                    delivered_at=_dt_to_ts(s.delivered_at) if s.delivered_at else None,
                    read_at=_dt_to_ts(s.read_at) if s.read_at else None,
                ) for s in statuses
            ])

        return pb
    

    async def MarkAsDelivered(self, request: mess_pb2.MarkAsDeliveredRequest, context):
        user_uuid = await self._require_current_user(context)
        chat_uuid = uuid.UUID(request.chat_id)
        message_id = request.message_id

        async with AsyncSessionLocal() as session:
            msg = await session.get(Message, (message_id, ))  # нужно указать составной ключ
            if not msg or msg.chat_id != chat_uuid:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Message not found")

            status = await session.execute(
                select(MessageStatus).where(
                    MessageStatus.message_id == message_id,
                    MessageStatus.user_id == user_uuid,
                )
            ).scalar_one_or_none()

            if not status:
                # не участник чата или статус не создан (отправитель не имеет статуса)
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a recipient")

            if not status.delivered_at:
                status.delivered_at = datetime.datetime.now(datetime.timezone.utc)
                await session.commit()
        return Empty()

    async def MarkAsRead(self, request: mess_pb2.MarkAsReadRequest, context):
        user_uuid = await self._require_current_user(context)
        chat_uuid = uuid.UUID(request.chat_id)
        message_id = request.message_id

        async with AsyncSessionLocal() as session:
            msg = await session.get(Message, (message_id, ))  # аналогично
            if not msg or msg.chat_id != chat_uuid:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Message not found")

            status = await session.execute(
                select(MessageStatus).where(
                    MessageStatus.message_id == message_id,
                    MessageStatus.user_id == user_uuid,
                )
            ).scalar_one_or_none()

            if not status:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not a recipient")

            if not status.read_at:
                status.read_at = datetime.datetime.now(datetime.timezone.utc)
                # при прочтении можно автоматически проставить delivered_at, если отсутствует
                if not status.delivered_at:
                    status.delivered_at = status.read_at
                await session.commit()
        return Empty()
    
    async def _get_message(self, session, message_id: int) -> Message:
        result = await session.execute(
            select(Message).where(Message.message_id == message_id, Message.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()