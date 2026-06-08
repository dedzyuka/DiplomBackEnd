import anyio
import strawberry
from typing import List
from FastApiClient.graphql.context import GraphQLContext
from .types import CallInfo

@strawberry.type
class CallQueries:
    @strawberry.field
    async def getLiveKitToken(self, call_id: str, info: strawberry.Info[GraphQLContext]) -> str:
        access_token = info.context.require_access_token()
        def _call():
            return info.context.call_client.get_livekit_token(
                call_id=call_id,
                access_token=access_token,
            )
        response = await anyio.to_thread.run_sync(_call)
        return response.token
    @strawberry.field
    async def get_call(self, info: strawberry.Info[GraphQLContext], call_id: str) -> CallInfo:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            resp = info.context.call_client.get_call(
                call_id=call_id,
                access_token=access_token,
                current_user_id=current_user_id,
            )
            return CallInfo(
                call_id=resp.call_id,
                chat_id=resp.chat_id,
                initiator_id=resp.initiator_id,
                status=resp.status,
                type=resp.type,
                started_at=resp.started_at,
                ended_at=resp.ended_at if hasattr(resp, 'ended_at') else None,
            )
        return await anyio.to_thread.run_sync(_call)

    @strawberry.field
    async def list_calls(self, info: strawberry.Info[GraphQLContext], chat_id: str, page: int = 1, page_size: int = 20) -> List[CallInfo]:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            resp = info.context.call_client.list_calls(
                chat_id=chat_id,
                page=page,
                page_size=page_size,
                access_token=access_token,
                current_user_id=current_user_id,
            )
            return [
                CallInfo(
                    call_id=c.call_id,
                    chat_id=c.chat_id,
                    initiator_id=c.initiator_id,
                    status=c.status,
                    type=c.type,
                    started_at=c.started_at,
                    ended_at=c.ended_at if hasattr(c, 'ended_at') else None,
                )
                for c in resp.calls
            ]
        return await anyio.to_thread.run_sync(_call)