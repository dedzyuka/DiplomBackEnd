from typing import List, Optional

import strawberry

from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.graphql.domain.contact.types import Contact
from FastApiClient.graphql.domain.contact.utils import from_grpc_contact


@strawberry.type
class ContactQueries:
    @strawberry.field
    async def list(
        self,
        info: strawberry.Info[GraphQLContext],
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> List[Contact]:
        current_user_id = info.context.require_user_id()
        access_token = info.context.require_access_token()

        normalized_status = status.strip().lower() if status else None
        allowed = {None, "pending", "accepted", "blocked"}

        if normalized_status not in allowed:
            raise ValueError("status must be one of: pending, accepted, blocked")

        response = info.context.contact_client.list_contacts(
            user_id=current_user_id,
            status=normalized_status,
            page=page,
            page_size=page_size,
            access_token=access_token,
        )
        contacts = []
        for grpc_contact in response.contacts:
            contact = from_grpc_contact(grpc_contact)
            # Добавляем онлайн-статус для contact_user, если он есть
            if contact.contact_user:
                is_online = await info.context.redis_client.sismember("ws:online_users", contact.contact_user.user_id)
                contact.contact_user.is_online = is_online
            contacts.append(contact)
        return contacts


    @strawberry.field
    async def pending(
        self,
        info: strawberry.Info[GraphQLContext],
        page: int = 1,
        page_size: int = 20,
    ) -> List[Contact]:
        """
        Исходящие заявки текущего пользователя.
        user_id = current_user_id AND status = pending
        """
        current_user_id = info.context.require_user_id()
        access_token = info.context.require_access_token()

        response = info.context.contact_client.list_contacts(
            user_id=current_user_id,
            status="pending",
            page=page,
            page_size=page_size,
            access_token=access_token,
        )

        return [from_grpc_contact(contact) for contact in response.contacts]

    @strawberry.field
    async def incoming(
        self,
        info: strawberry.Info[GraphQLContext],
        page: int = 1,
        page_size: int = 20,
    ) -> List[Contact]:
        # аналогично, для каждого contact_user добавляем is_online
        current_user_id = info.context.require_user_id()
        access_token = info.context.require_access_token()
        response = info.context.contact_client.list_incoming_contacts(
            user_id=current_user_id,
            page=page,
            page_size=page_size,
            access_token=access_token,
        )
        contacts = []
        for grpc_contact in response.contacts:
            contact = from_grpc_contact(grpc_contact)
            if contact.contact_user:
                is_online = await info.context.redis_client.sismember("ws:online_users", contact.contact_user.user_id)
                contact.contact_user.is_online = is_online
            contacts.append(contact)
        return contacts

    @strawberry.field
    async def accepted(
        self,
        info: strawberry.Info[GraphQLContext],
        page: int = 1,
        page_size: int = 20,
    ) -> List[Contact]:
        current_user_id = info.context.require_user_id()
        access_token = info.context.require_access_token()

        response = info.context.contact_client.list_contacts(
            user_id=current_user_id,
            status="accepted",
            page=page,
            page_size=page_size,
            access_token=access_token,
        )

        return [from_grpc_contact(contact) for contact in response.contacts]