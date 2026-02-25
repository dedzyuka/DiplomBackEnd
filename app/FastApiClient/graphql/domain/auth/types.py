import strawberry

from FastApiClient.graphql.domain.user.types import User


@strawberry.type
class AuthTokens:
    access_token: str
    refresh_token: str
    expires_in: int


@strawberry.type
class AuthPayload:
    tokens: AuthTokens
    user: User