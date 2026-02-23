import strawberry
from typing import Optional

@strawberry.type
class User:
    user_id: str
    nick_name: str
    first_name:str
    last_name:str
    middle_name:str
    email: str
    phone: str
    avatar_url:str
    bio:str
    last_seen:str
    is_online:str
    status:str
    email_verified:str
    phone_verified:str
    is_admin:str
    created_at:str
    updated_at:str
    
@strawberry.type
class PrivacySetting:
    setting: str