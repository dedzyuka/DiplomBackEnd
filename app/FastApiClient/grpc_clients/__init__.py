from .user import UserGrpcClient
from .auth import AuthGrpcClient

# Создаём экземпляры клиентов (синглтоны)
user_client = UserGrpcClient()
auth_client = AuthGrpcClient()