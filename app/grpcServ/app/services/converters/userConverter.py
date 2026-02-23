from google.protobuf.timestamp_pb2 import Timestamp
from services.models import User as DbUser  # импортируем вашу SQLAlchemy модель
from protobuf import mess_pb2

def db_user_to_proto(db_user: DbUser) -> mess_pb2.User:
    """
    Преобразует объект пользователя из БД в protobuf-сообщение User.
    """
    # Обязательные поля (всегда должны быть)
    kwargs = {
        "user_id": str(db_user.user_id),            # UUID -> строка
        "nick_name": db_user.nick_name or "",       # строка, если None -> пустая строка
        "is_online": bool(db_user.is_online),
        "email_verified": bool(db_user.email_verified),
        "phone_verified": bool(db_user.phone_verified),
        "is_admin": bool(db_user.is_admin),
    }

    # Опциональные строки — добавляем только если значение не None
    # (можно также всегда добавлять с or "", но тогда клиент получит пустую строку вместо отсутствия поля)
    optional_string_fields = [
        "first_name", "last_name", "middle_name",
        "email", "phone", "avatar_url", "bio"
    ]
    for field in optional_string_fields:
        value = getattr(db_user, field, None)
        if value is not None:
            kwargs[field] = value

    # Enum status (предполагаем, что AccountStatus имеет атрибут .value)
    if db_user.status is not None:
        kwargs["status"] = str(db_user.status.value).upper()
    else:
        # Если статус обязателен, но вдруг None, ставим значение по умолчанию (например, 0)
        kwargs["status"] = 0  # или db_user.status.value, если есть дефолт

    # Timestamp поля
    timestamp_fields = ["created_at", "updated_at", "last_seen"]
    for field in timestamp_fields:
        dt = getattr(db_user, field, None)
        if dt is not None:
            ts = Timestamp()
            ts.FromDatetime(dt)
            kwargs[field] = ts
        # Если dt == None, просто не включаем поле — protobuf оставит его пустым

    return mess_pb2.User(**kwargs)