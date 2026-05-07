import strawberry

from FastApiClient.graphql.domain.user.queries import UserQueries
from FastApiClient.graphql.domain.user.mutations import UserMutations
from FastApiClient.graphql.domain.auth.queries import AuthQueries
from FastApiClient.graphql.domain.auth.mutations import AuthMutations
from FastApiClient.graphql.domain.chat.queries import ChatQueries
from FastApiClient.graphql.domain.chat.mutations import ChatMutations
from FastApiClient.graphql.domain.message.queries import MessageQueries
from FastApiClient.graphql.domain.message.mutations import MessageMutations

from FastApiClient.graphql.domain.contact.queries import ContactQueries
from FastApiClient.graphql.domain.contact.mutations import ContactMutations


@strawberry.type
class Query:
    user: UserQueries = strawberry.field(resolver=lambda: UserQueries())
    auth: AuthQueries = strawberry.field(resolver=lambda: AuthQueries())
    chat: ChatQueries = strawberry.field(resolver=lambda: ChatQueries())
    message: MessageQueries = strawberry.field(resolver=lambda: MessageQueries())
    contact: ContactQueries = strawberry.field(resolver=lambda: ContactQueries())

@strawberry.type
class Mutation:
    user: UserMutations = strawberry.field(resolver=lambda: UserMutations())
    auth: AuthMutations = strawberry.field(resolver=lambda: AuthMutations())
    chat: ChatMutations = strawberry.field(resolver=lambda: ChatMutations())
    message: MessageMutations = strawberry.field(resolver=lambda: MessageMutations())
    contact: ContactMutations = strawberry.field(resolver=lambda: ContactMutations())

schema = strawberry.Schema(query=Query, mutation=Mutation)