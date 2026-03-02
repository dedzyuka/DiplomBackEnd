import strawberry
from FastApiClient.graphql.domain.user.queries import UserQueries
from FastApiClient.graphql.domain.user.mutations import UserMutations
from FastApiClient.graphql.domain.auth.mutations import AuthMutations
# from FastApiClient.graphql.domain.chat.queries import ChatQueries
from FastApiClient.graphql.domain.chat.mutations import ChatMutations


@strawberry.type
class Query:
    user: UserQueries = strawberry.field(resolver=lambda: UserQueries())
    # chat: ChatQueries = strawberry.field(resolver=lambda: ChatQueries())


@strawberry.type
class Mutation:
    user: UserMutations = strawberry.field(resolver=lambda: UserMutations())
    auth: AuthMutations = strawberry.field(resolver=lambda: AuthMutations())
    chat: ChatMutations = strawberry.field(resolver=lambda: ChatMutations())


schema = strawberry.Schema(query=Query, mutation=Mutation)
