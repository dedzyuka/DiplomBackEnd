import strawberry
from typing import Optional
from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.utils.converter import from_grpc_user
from .types import User, PrivacySetting

@strawberry.type
class UserMutations:
    @strawberry.mutation
    async def create(self, nick_name: str, email: str,password:str,phone:str, info: strawberry.Info[GraphQLContext]) -> User:
        """Создать нового пользователя."""
        grpc_user = info.context.user_client.create_user(nick_name, email,password,phone)
        print(grpc_user)
        return from_grpc_user(grpc_user)

    @strawberry.mutation
    async def update(self, 
                    user_id: str, 
                    info: strawberry.Info[GraphQLContext],
                    nick_name: Optional[str] = None, 
                    email: Optional[str] = None,
                    first_name: Optional[str] = None,
                    last_name: Optional[str] = None,
                    middle_name: Optional[str] = None,
                    phone: Optional[str] = None,
                    avatar_url: Optional[str] = None,
                    bio: Optional[str] = None
                    ) -> Optional[User]:
        """Обновить данные пользователя."""
        # Передаём текущие значения, если новые не указаны (можно улучшить)
        grpc_user = info.context.user_client.update_user(user_id, 
                                                         nick_name or "", 
                                                         email or "",
                                                         first_name or "",
                                                         last_name or "",
                                                         middle_name or "",
                                                         phone or "",
                                                         avatar_url or "",
                                                         bio or "")
        return from_grpc_user(grpc_user)

    @strawberry.mutation
    async def delete(self, id: int, info: strawberry.Info[GraphQLContext]) -> bool:
        """Удалить пользователя."""
        info.context.user_client.delete_user(id)
        return True

    @strawberry.mutation
    async def update_privacy(self, setting: str, info: strawberry.Info[GraphQLContext]) -> PrivacySetting:
        """Обновить настройки приватности."""
        response = info.context.user_client.update_privacy(setting)
        return PrivacySetting(setting=response.setting)