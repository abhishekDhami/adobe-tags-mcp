from __future__ import annotations

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from app.clients import ApiError, to_tool_error
from app.context import AppContext
from app.models import HealthResult, SystemStatusResult


def register_system_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_system_health(
        ctx: Context[ServerSession, AppContext],
    ) -> HealthResult:
        """Check whether the local Adobe Tags API process is reachable and healthy.

        Use this no-argument tool for a lightweight connectivity check. It does not
        return detailed runtime information and does not require API authentication.
        """
        try:
            return await ctx.request_context.lifespan_context.api.get_health()
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def get_system_status(
        ctx: Context[ServerSession, AppContext],
    ) -> SystemStatusResult:
        """Return detailed runtime status for the local Adobe Tags API.

        Use this no-argument tool when version, environment, uptime, current server
        time, or authentication configuration is needed.
        """
        try:
            return await ctx.request_context.lifespan_context.api.get_status()
        except ApiError as error:
            raise to_tool_error(error) from error
