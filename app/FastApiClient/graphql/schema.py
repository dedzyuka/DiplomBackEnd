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

from FastApiClient.graphql.domain.call.queries import CallQueries
from FastApiClient.graphql.domain.call.mutations import CallMutations


@strawberry.type
class Query:
    user: UserQueries = strawberry.field(resolver=lambda: UserQueries())
    auth: AuthQueries = strawberry.field(resolver=lambda: AuthQueries())
    chat: ChatQueries = strawberry.field(resolver=lambda: ChatQueries())
    message: MessageQueries = strawberry.field(resolver=lambda: MessageQueries())
    contact: ContactQueries = strawberry.field(resolver=lambda: ContactQueries())
    call: CallQueries = strawberry.field(resolver=lambda: CallQueries())

@strawberry.type
class Mutation:
    user: UserMutations = strawberry.field(resolver=lambda: UserMutations())
    auth: AuthMutations = strawberry.field(resolver=lambda: AuthMutations())
    chat: ChatMutations = strawberry.field(resolver=lambda: ChatMutations())
    message: MessageMutations = strawberry.field(resolver=lambda: MessageMutations())
    contact: ContactMutations = strawberry.field(resolver=lambda: ContactMutations())
    call: CallMutations = strawberry.field(resolver=lambda: CallMutations())

schema = strawberry.Schema(query=Query, mutation=Mutation)