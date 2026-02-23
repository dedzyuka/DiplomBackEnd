from enum import Enum

class ChatType(str, Enum):
    private = "private"
    group = "group"
    channel = "channel"

class MemberRole(str, Enum):
    owner = "owner"
    admin = "admin"
    member = "member"

class MemberStatus(str, Enum):
    active = "active"
    left = "left"
    banned = "banned"

class MessageType(str, Enum):
    text = "text"
    image = "image"
    video = "video"
    audio = "audio"
    file = "file"
    location = "location"
    contact = "contact"
    mixed = "mixed"

class ContactStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    blocked = "blocked"

class AccountStatus(str, Enum):
    active = "active"
    suspended = "suspended"
    deleted = "deleted"


class PrivacyLevel(str, Enum):
    everyone = "everyone"
    contacts = "contacts"
    nobody = "nobody"