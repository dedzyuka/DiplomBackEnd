from .chat import ChatGrpcClient
from .user import UserGrpcClient
from .auth import AuthGrpcClient
from .message import MessageGrpcClient
from .contact import ContactGrpcClient

message_client = MessageGrpcClient()
user_client = UserGrpcClient()
auth_client = AuthGrpcClient()
chat_client = ChatGrpcClient()
contact_client = ContactGrpcClient()