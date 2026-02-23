import strawberry
from FastApiClient.graphql.domain.user.types import User

@strawberry.type
class LoginResponse:
    token: str
    user: User