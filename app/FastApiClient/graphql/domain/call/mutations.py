import anyio
import strawberry
from FastApiClient.graphql.context import GraphQLContext
from .types import StartCallInput, AcceptCallInput, RejectCallInput, EndCallInput, GetLiveKitTokenInput, CallInfo

@strawberry.type
class CallMutations:
    @strawberry.mutation
    async def start_call(self, info: strawberry.Info[GraphQLContext], input: StartCallInput) -> CallInfo:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            resp = info.context.call_client.start_call(
                chat_id=input.chat_id,
                type=input.type,
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

    @strawberry.mutation
    async def accept_call(self, info: strawberry.Info[GraphQLContext], input: AcceptCallInput) -> CallInfo:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            resp = info.context.call_client.accept_call(
                call_id=input.call_id,
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

    @strawberry.mutation
    async def reject_call(self, info: strawberry.Info[GraphQLContext], input: RejectCallInput) -> bool:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            info.context.call_client.reject_call(
                call_id=input.call_id,
                access_token=access_token,
                current_user_id=current_user_id,
            )
            return True
        return await anyio.to_thread.run_sync(_call)

    @strawberry.mutation
    async def end_call(self, info: strawberry.Info[GraphQLContext], input: EndCallInput) -> bool:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            info.context.call_client.end_call(
                call_id=input.call_id,
                access_token=access_token,
                current_user_id=current_user_id,
            )
            return True
        return await anyio.to_thread.run_sync(_call)

    @strawberry.mutation
    async def get_livekit_token(self, info: strawberry.Info[GraphQLContext], input: GetLiveKitTokenInput) -> str:
        access_token = info.context.require_access_token()
        current_user_id = info.context.require_user_id()
        def _call():
            resp = info.context.call_client.get_livekit_token(
                call_id=input.call_id,
                access_token=access_token,
                current_user_id=current_user_id,
            )
            return resp.token
        return await anyio.to_thread.run_sync(_call)