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
    user: User

    @strawberry.field
    def access_token(self) -> str:
        return self.tokens.access_token

    @strawberry.field
    def refresh_token(self) -> str:
        return self.tokens.refresh_token

    @strawberry.field
    def expires_in(self) -> int:
        return self.tokens.expires_in