from typing import Optional

import strawberry

from FastApiClient.graphql.domain.user.types import User


@strawberry.type
class Contact:
    user_id: str
    contact_user_id: str
    status: str
    created_at: str = ""
    updated_at: str = ""
    contact_user: Optional[User] = None