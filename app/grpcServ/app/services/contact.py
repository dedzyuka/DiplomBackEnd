from datetime import datetime, timezone
import uuid

import grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from database import AsyncSessionLocal
from protobuf import mess_pb2, mess_pb2_grpc
from services.access_session import require_current_user_id
from services.enums import AccountStatus as DbAccountStatus
from services.enums import ContactStatus as DbContactStatus
from services.models import Contacts as Contact, Users as User
from services.converters.userConverter import db_user_to_proto



class ContactServicer(mess_pb2_grpc.ContactServiceServicer):
    _STATUS_PROTO_TO_DB = {
        mess_pb2.ContactStatus.PENDING: DbContactStatus.pending,
        mess_pb2.ContactStatus.ACCEPTED: DbContactStatus.accepted,
        mess_pb2.ContactStatus.BLOCKED: DbContactStatus.blocked,
    }

    _STATUS_DB_TO_PROTO = {
        "pending": mess_pb2.ContactStatus.PENDING,
        "accepted": mess_pb2.ContactStatus.ACCEPTED,
        "blocked": mess_pb2.ContactStatus.BLOCKED,
    }

    async def _require_current_user_id(self, context) -> str:
        return await require_current_user_id(context)

    @staticmethod
    def _parse_uuid(value: str, field_name: str, context) -> uuid.UUID:
        try:
            return uuid.UUID((value or "").strip())
        except Exception:
            raise ValueError(f"Invalid {field_name}")

    def _status_to_proto(self, status) -> int:
        raw = getattr(status, "value", status)
        return self._STATUS_DB_TO_PROTO.get(
            str(raw),
            mess_pb2.ContactStatus.CONTACT_STATUS_UNSPECIFIED,
        )

    def _contact_to_proto(self, contact: Contact) -> mess_pb2.Contact:
        result = mess_pb2.Contact(
            user_id=str(contact.user_id),
            contact_user_id=str(contact.contact_user_id),
            status=self._status_to_proto(contact.status),
        )

        if contact.created_at:
            ts = Timestamp()
            ts.FromDatetime(contact.created_at)
            result.created_at.CopyFrom(ts)

        if contact.updated_at:
            ts = Timestamp()
            ts.FromDatetime(contact.updated_at)
            result.updated_at.CopyFrom(ts)


        state = inspect(contact)

        if "contact_user" not in state.unloaded and contact.contact_user is not None:
            result.contact_user.CopyFrom(db_user_to_proto(contact.contact_user))

        return result
    
    async def _get_contact_with_user(
        self,
        session,
        user_id: uuid.UUID,
        contact_user_id: uuid.UUID,
    ) -> Contact | None:
        stmt = (
            select(Contact)
            .options(selectinload(Contact.contact_user))
            .where(
                Contact.user_id == user_id,
                Contact.contact_user_id == contact_user_id,
            )
        )

        return (await session.execute(stmt)).scalars().first()

    async def _ensure_target_user_exists(self, session, contact_user_id: uuid.UUID, context):
        target = await session.get(User, contact_user_id)
        if not target or target.status == DbAccountStatus.deleted:
            await context.abort(grpc.StatusCode.NOT_FOUND, "Contact user not found")
        return target

    async def AddContact(self, request, context):
        current_user_id = await self._require_current_user_id(context)

        if current_user_id != request.user_id:
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "Cannot add contact for another user",
            )

        try:
            user_uuid = self._parse_uuid(request.user_id, "user_id", context)
            contact_uuid = self._parse_uuid(request.contact_user_id, "contact_user_id", context)
        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))

        if user_uuid == contact_uuid:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Cannot add yourself")

        async with AsyncSessionLocal() as session:
            await self._ensure_target_user_exists(session, contact_uuid, context)

            
            existing = await self._get_contact_with_user(
                session,
                user_uuid,
                contact_uuid,
            )

            if existing:
                return self._contact_to_proto(existing)

            contact = Contact(
                user_id=user_uuid,
                contact_user_id=contact_uuid,
                status=DbContactStatus.pending,
            )

            session.add(contact)

            try:
                await session.commit()

                contact_with_user = await self._get_contact_with_user(
                    session,
                    user_uuid,
                    contact_uuid,
                )

                return self._contact_to_proto(contact_with_user)
            except IntegrityError:
                await session.rollback()
                await context.abort(grpc.StatusCode.ALREADY_EXISTS, "Contact already exists")

    async def AcceptContact(self, request, context):
        current_user_id = await self._require_current_user_id(context)

        if current_user_id != request.user_id:
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "Cannot accept contact for another user",
            )

        try:
            user_uuid = self._parse_uuid(request.user_id, "user_id", context)
            contact_uuid = self._parse_uuid(request.contact_user_id, "contact_user_id", context)
        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))

        async with AsyncSessionLocal() as session:
            # Входящий запрос: другой пользователь уже добавил меня.
            incoming = await session.get(Contact, (contact_uuid, user_uuid))
            if not incoming:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Incoming contact request not found")

            incoming.status = DbContactStatus.accepted
            incoming.updated_at = datetime.now(timezone.utc)

            # Для удобства создаём зеркальную запись.
            stmt = (
                select(Contact)
                .where(Contact.user_id == user_uuid, Contact.contact_user_id == contact_uuid)
                .options(selectinload(Contact.contact_user))
            )
            result = await session.execute(stmt)
            outgoing = result.scalar_one_or_none()
            if not outgoing:
                outgoing = Contact(
                    user_id=user_uuid,
                    contact_user_id=contact_uuid,
                    status=DbContactStatus.accepted,
                )
                session.add(outgoing)
            else:
                outgoing.status = DbContactStatus.accepted
                outgoing.updated_at = datetime.now(timezone.utc)

            await session.commit()

            outgoing_with_user = await self._get_contact_with_user(
                session,
                user_uuid,
                contact_uuid,
            )

            return self._contact_to_proto(outgoing_with_user)

    async def BlockContact(self, request, context):
        current_user_id = await self._require_current_user_id(context)

        if current_user_id != request.user_id:
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "Cannot block contact for another user",
            )

        try:
            user_uuid = self._parse_uuid(request.user_id, "user_id", context)
            contact_uuid = self._parse_uuid(request.contact_user_id, "contact_user_id", context)
        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))

        if user_uuid == contact_uuid:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Cannot block yourself")

        async with AsyncSessionLocal() as session:
            await self._ensure_target_user_exists(session, contact_uuid, context)

            stmt = (
                select(Contact)
                .where(Contact.user_id == user_uuid, Contact.contact_user_id == contact_uuid)
                .options(selectinload(Contact.contact_user))
            )
            result = await session.execute(stmt)
            contact = result.scalar_one_or_none()
            if not contact:
                contact = Contact(
                    user_id=user_uuid,
                    contact_user_id=contact_uuid,
                    status=DbContactStatus.blocked,
                )
                session.add(contact)
            else:
                contact.status = DbContactStatus.blocked
                contact.updated_at = datetime.now(timezone.utc)

            await session.commit()

            contact_with_user = await self._get_contact_with_user(
                session,
                user_uuid,
                contact_uuid,
            )

            return self._contact_to_proto(contact_with_user)

    async def RemoveContact(self, request, context):
        current_user_id = await self._require_current_user_id(context)
        if current_user_id != request.user_id:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Cannot remove contact for another user")
        user_uuid = uuid.UUID(request.user_id)
        contact_uuid = uuid.UUID(request.contact_user_id)
        async with AsyncSessionLocal() as session:
            # Удаляем обе записи
            from sqlalchemy import and_, or_
            stmt = delete(Contact).where(
                or_(
                    and_(Contact.user_id == user_uuid, Contact.contact_user_id == contact_uuid),
                    and_(Contact.user_id == contact_uuid, Contact.contact_user_id == user_uuid)
                )
            )
            await session.execute(stmt)
            await session.commit()
            return Empty()

    # app/grpcServ/app/services/contact.py
# Найти метод ListContacts (примерно строка 180)

    async def ListContacts(self, request, context):
        current_user_id = await self._require_current_user_id(context)
        if current_user_id != request.user_id:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Cannot list contacts for another user")
        user_uuid = uuid.UUID(request.user_id)
        page_size = max(1, min(request.page_size or 20, 100))
        offset = int(request.page_token or "0") if request.page_token else 0
        async with AsyncSessionLocal() as session:
            # ДОБАВЛЯЕМ selectinload для подгрузки связанного пользователя
            stmt = (
                select(Contact)
                .options(selectinload(Contact.contact_user))   # <-- ЭТО КЛЮЧЕВОЕ ИЗМЕНЕНИЕ
                .where(
                    Contact.user_id == user_uuid,
                    Contact.status == DbContactStatus.accepted
                )
                .order_by(Contact.updated_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            contacts = (await session.execute(stmt)).scalars().all()

            next_offset = offset + len(contacts)
            next_page_token = str(next_offset) if len(contacts) == page_size else ""

            return mess_pb2.ContactsListResponse(
                contacts=[self._contact_to_proto(contact) for contact in contacts],
                next_page_token=next_page_token,
                total_count=0,
            )
        
    async def ListIncomingContacts(self, request, context):
        current_user_id = await self._require_current_user_id(context)

        if current_user_id != request.user_id:
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "Cannot list incoming contacts for another user",
            )

        try:
            user_uuid = self._parse_uuid(request.user_id, "user_id", context)
        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))

        page_size = max(1, min(request.page_size or 20, 100))

        try:
            offset = int(request.page_token or "0")
        except ValueError:
            offset = 0

        async with AsyncSessionLocal() as session:
            stmt = (
                select(Contact)
                .options(selectinload(Contact.user))
                .where(
                    Contact.contact_user_id == user_uuid,
                    Contact.status == DbContactStatus.pending,
                )
                .order_by(Contact.updated_at.desc())
                .offset(offset)
                .limit(page_size)
            )

            contacts = (await session.execute(stmt)).scalars().all()

            result_contacts = []

            for contact in contacts:
                result = mess_pb2.Contact(
                    user_id=str(contact.user_id),
                    contact_user_id=str(contact.contact_user_id),
                    status=self._status_to_proto(contact.status),
                )

                if contact.created_at:
                    ts = Timestamp()
                    ts.FromDatetime(contact.created_at)
                    result.created_at.CopyFrom(ts)

                if contact.updated_at:
                    ts = Timestamp()
                    ts.FromDatetime(contact.updated_at)
                    result.updated_at.CopyFrom(ts)

                # Для входящей заявки contact_user должен быть отправитель заявки,
                # то есть contact.user, а не contact.contact_user.
                if getattr(contact, "user", None):
                    result.contact_user.CopyFrom(db_user_to_proto(contact.user))

                result_contacts.append(result)

            next_offset = offset + len(contacts)
            next_page_token = str(next_offset) if len(contacts) == page_size else ""

            return mess_pb2.ContactsListResponse(
                contacts=result_contacts,
                next_page_token=next_page_token,
                total_count=0,
            )