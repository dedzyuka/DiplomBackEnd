from datetime import timezone

from FastApiClient.graphql.domain.contact.types import Contact
from FastApiClient.utils.converter import from_grpc_user
from FastApiClient.protos.protobuf import mess_pb2


def _ts_to_iso(ts) -> str:
    if ts is None:
        return ""

    try:
        dt = ts.ToDatetime()
    except Exception:
        return ""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.isoformat()


_CONTACT_STATUS_MAP = {
    mess_pb2.ContactStatus.PENDING: "pending",
    mess_pb2.ContactStatus.ACCEPTED: "accepted",
    mess_pb2.ContactStatus.BLOCKED: "blocked",
    mess_pb2.ContactStatus.CONTACT_STATUS_UNSPECIFIED: "unspecified",
}


def from_grpc_contact(grpc_contact: mess_pb2.Contact) -> Contact:
    contact_user = None

    if grpc_contact.HasField("contact_user"):
        contact_user = from_grpc_user(grpc_contact.contact_user)

    return Contact(
        user_id=grpc_contact.user_id,
        contact_user_id=grpc_contact.contact_user_id,
        status=_CONTACT_STATUS_MAP.get(grpc_contact.status, "unspecified"),
        created_at=_ts_to_iso(grpc_contact.created_at),
        updated_at=_ts_to_iso(grpc_contact.updated_at),
        contact_user=contact_user,
    )