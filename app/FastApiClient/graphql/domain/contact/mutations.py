import strawberry

from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.graphql.domain.contact.types import Contact
from FastApiClient.graphql.domain.contact.utils import from_grpc_contact


@strawberry.type
class ContactMutations:
    @strawberry.mutation
    async def add(
        self,
        contact_user_id: str,
        info: strawberry.Info[GraphQLContext],
    ) -> Contact:
        current_user_id = info.context.require_user_id()
        access_token = info.context.require_access_token()

        response = info.context.contact_client.add_contact(
            user_id=current_user_id,
            contact_user_id=contact_user_id,
            access_token=access_token,
        )

        return from_grpc_contact(response)

    @strawberry.mutation
    async def accept(
        self,
        contact_user_id: str,
        info: strawberry.Info[GraphQLContext],
    ) -> Contact:
        current_user_id = info.context.require_user_id()
        access_token = info.context.require_access_token()

        response = info.context.contact_client.accept_contact(
            user_id=current_user_id,
            contact_user_id=contact_user_id,
            access_token=access_token,
        )

        return from_grpc_contact(response)

    @strawberry.mutation
    async def block(
        self,
        contact_user_id: str,
        info: strawberry.Info[GraphQLContext],
    ) -> Contact:
        current_user_id = info.context.require_user_id()
        access_token = info.context.require_access_token()

        response = info.context.contact_client.block_contact(
            user_id=current_user_id,
            contact_user_id=contact_user_id,
            access_token=access_token,
        )

        return from_grpc_contact(response)

    @strawberry.mutation
    async def remove(
        self,
        contact_user_id: str,
        info: strawberry.Info[GraphQLContext],
    ) -> bool:
        current_user_id = info.context.require_user_id()
        access_token = info.context.require_access_token()

        info.context.contact_client.remove_contact(
            user_id=current_user_id,
            contact_user_id=contact_user_id,
            access_token=access_token,
        )

        return True