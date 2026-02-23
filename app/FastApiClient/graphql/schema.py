import strawberry
from FastApiClient.graphql.domain.user.queries import UserQueries
from FastApiClient.graphql.domain.user.mutations import UserMutations
from FastApiClient.graphql.domain.auth.mutations import AuthMutations

@strawberry.type
class Query:
    user: UserQueries = strawberry.field(resolver=lambda: UserQueries())
    # Здесь можно добавить другие группы, например, product

@strawberry.type
class Mutation:
    user: UserMutations = strawberry.field(resolver=lambda: UserMutations())
    auth: AuthMutations = strawberry.field(resolver=lambda: AuthMutations())

schema = strawberry.Schema(query=Query, mutation=Mutation)