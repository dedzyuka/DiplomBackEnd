import anyio
import strawberry

from FastApiClient.graphql.context import GraphQLContext
from .types import SessionInfo


@strawberry.type
class AuthQueries:
    @strawberry.field
    async def sessions(self, info: strawberry.Info[GraphQLContext]) -> list[SessionInfo]:
        access_token = info.context.require_access_token()

        response = await anyio.to_thread.run_sync(
            lambda: info.context.auth_client.list_sessions(access_token)
        )

        return [
            SessionInfo(
                session_id=item.session_id,
                device_info=item.device_info or None,
                user_agent=item.user_agent or None,
                ip_address=item.ip_address or None,
                created_at=item.created_at,
                last_seen_at=item.last_seen_at or None,
                is_current=item.is_current,
            )
            for item in response.sessions
        ]