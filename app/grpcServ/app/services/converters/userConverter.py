from google.protobuf.timestamp_pb2 import Timestamp

from protobuf import mess_pb2
from services.models import Users as DbUser


_STATUS_NAME_TO_PROTO = {
    "active": mess_pb2.AccountStatus.ACTIVE,
    "suspended": mess_pb2.AccountStatus.SUSPENDED,
    "deleted": mess_pb2.AccountStatus.DELETED,
}


def _resolve_status(db_user: DbUser) -> int:
    raw_status = getattr(db_user, "status", None)
    if raw_status is None:
        return mess_pb2.AccountStatus.ACCOUNT_STATUS_UNSPECIFIED

    enum_value = getattr(raw_status, "value", raw_status)
    enum_name = str(enum_value).strip().lower()
    return _STATUS_NAME_TO_PROTO.get(
        enum_name,
        mess_pb2.AccountStatus.ACCOUNT_STATUS_UNSPECIFIED,
    )


def db_user_to_proto(db_user: DbUser) -> mess_pb2.User:
    """Convert SQLAlchemy user model to protobuf User."""
    kwargs = {
        "user_id": str(db_user.user_id),
        "nick_name": db_user.nick_name or "",
        "is_online": bool(db_user.is_online),
        "status": _resolve_status(db_user),
        "email_verified": bool(db_user.email_verified),
        "phone_verified": bool(db_user.phone_verified),
        "is_admin": bool(db_user.is_admin),
    }

    for field in [
        "first_name",
        "last_name",
        "middle_name",
        "email",
        "phone",
        "avatar_url",
        "bio",
    ]:
        value = getattr(db_user, field, None)
        if value is not None:
            kwargs[field] = value

    for field in ["created_at", "updated_at", "last_seen"]:
        dt = getattr(db_user, field, None)
        if dt is not None:
            ts = Timestamp()
            ts.FromDatetime(dt)
            kwargs[field] = ts

    return mess_pb2.User(**kwargs)