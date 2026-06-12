import strawberry
from typing import Optional

@strawberry.type
class CallInfo:
    call_id: str
    chat_id: str
    initiator_id: str
    status: str
    type: str
    started_at: str
    ended_at: Optional[str] = None

@strawberry.input
class StartCallInput:
    chat_id: str
    type: str  # "audio" или "video"

@strawberry.input
class AcceptCallInput:
    call_id: str

@strawberry.input
class RejectCallInput:
    call_id: str

@strawberry.input
class EndCallInput:
    call_id: str

@strawberry.input
class GetLiveKitTokenInput:
    call_id: str

@strawberry.type
class LiveKitTokenResult:
    token: str
    ws_url: str