from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from pydantic import Field

from app.clients import ApiError, to_tool_error
from app.context import AppContext
from app.models.libraries import (
    DevLibraryCandidateResult,
    DevelopmentLibraryReviewResult,
    EnvironmentListResult,
    LibraryDetail,
    LibraryResourcesResult,
    PaginatedLibraries,
    PropertyActivityResult,
    SessionState,
)


def register_library_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_environments(
        ctx: Context[ServerSession, AppContext],
        property_id: Annotated[str, Field(description="Adobe Tags property ID (PR...).")],
    ) -> EnvironmentListResult:
        """List environments (development, staging, production) for a property."""
        try:
            return await ctx.request_context.lifespan_context.api.list_environments(property_id)
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def list_published_libraries(
        ctx: Context[ServerSession, AppContext],
        property_id: Annotated[str, Field(description="Adobe Tags property ID (PR...).")],
        page: Annotated[int, Field(ge=1, description="Page number (1-based). Increment for next page.")] = 1,
        page_size: Annotated[int, Field(ge=0, le=100, description="Items per page (default 25).")] = 0,
        state: Annotated[
            str,
            Field(description="Library state filter. Defaults to published (historical snapshots)."),
        ] = "published",
        environment_id: Annotated[str | None, Field(description="Optional environment ID filter.")] = None,
        sort: Annotated[
            str,
            Field(description="Sort order. Default -published_at = newest publish first."),
        ] = "-published_at",
    ) -> PaginatedLibraries:
        """List published libraries — audit/history of what went through publish.

        Check data.pagination.hasNextPage; if true, call again with page=page+1.
        """
        try:
            return await ctx.request_context.lifespan_context.api.list_published_libraries(
                property_id,
                page=page,
                page_size=page_size,
                state=state,
                environment_id=environment_id,
                sort=sort,
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def get_development_library(
        ctx: Context[ServerSession, AppContext],
        property_id: Annotated[str, Field(description="Adobe Tags property ID (PR...).")],
    ) -> DevLibraryCandidateResult:
        """Get the active development library for pre-publish review.

        Returns status=resolved with one library, or status=ambiguous with candidates
        when multiple development libraries exist. Never silently picks one.
        """
        try:
            return await ctx.request_context.lifespan_context.api.get_development_library(property_id)
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def get_library(
        ctx: Context[ServerSession, AppContext],
        library_id: Annotated[str, Field(description="Adobe Tags library ID (LB...).")],
    ) -> LibraryDetail:
        """Get one library with environment, property, and build context."""
        try:
            return await ctx.request_context.lifespan_context.api.get_library(library_id)
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def list_library_resources(
        ctx: Context[ServerSession, AppContext],
        library_id: Annotated[str, Field(description="Adobe Tags library ID (LB...).")],
        resource_type: Annotated[
            str,
            Field(description="all, rules, data_elements, or extensions."),
        ] = "all",
        page: Annotated[int, Field(ge=1)] = 1,
        page_size: Annotated[int, Field(ge=0, le=100)] = 0,
    ) -> LibraryResourcesResult:
        """List resources in a library with version, dirty, and changeKind fields."""
        try:
            return await ctx.request_context.lifespan_context.api.list_library_resources(
                library_id,
                resource_type=resource_type,
                page=page,
                page_size=page_size,
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def review_development_library(
        ctx: Context[ServerSession, AppContext],
        library_id: Annotated[str, Field(description="Development library ID (LB...).")],
        depth: Annotated[
            str,
            Field(
                description=(
                    "summary (default) or full. Start with summary. "
                    "Compare pending vs publishedLive; use those ids for follow-up get_* calls."
                ),
            ),
        ] = "summary",
    ) -> DevelopmentLibraryReviewResult:
        """Pre-publish review of a development library vs production.

        library_id must be a development-state library (not published/submitted/approved).
        For each change: changeKind new | modified | disabled.
        Compare pending (in library) vs publishedLive (production). See response idUsage.
        """
        try:
            return await ctx.request_context.lifespan_context.api.review_development_library(
                library_id,
                depth=depth,
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def get_property_activity(
        ctx: Context[ServerSession, AppContext],
        property_id: Annotated[str, Field(description="Adobe Tags property ID (PR...).")],
        from_date: Annotated[
            str | None,
            Field(
                description=(
                    "Window start YYYY-MM-DD or ISO-8601. Example for March 2025: 2025-03-01."
                ),
            ),
        ] = None,
        to_date: Annotated[
            str | None,
            Field(
                description=(
                    "Window end YYYY-MM-DD or ISO-8601. Example for March 2025: 2025-03-31."
                ),
            ),
        ] = None,
        focus: Annotated[
            str,
            Field(
                description=(
                    "all (default) = deployments + edit audit events; "
                    "deployments = published libraries only; edits = audit events only."
                ),
            ),
        ] = "all",
        prior_deploy_limit: Annotated[
            int,
            Field(
                ge=1,
                le=10,
                description=(
                    "If no deployments in the window, return this many publishes "
                    "strictly before the window start (not the newest overall)."
                ),
            ),
        ] = 3,
    ) -> PropertyActivityResult:
        """Answer who/when activity and deployments for a property in a time window.

        Deployments come from published libraries. Edits come from Adobe audit events.
        If no deployment falls in the window, priorToWindow lists the last N publishes
        before the window start (e.g. ask March 2025 → last 3 deploys before March 2025).
        """
        try:
            return await ctx.request_context.lifespan_context.api.get_property_activity(
                property_id,
                from_value=from_date,
                to_value=to_date,
                focus=focus,
                prior_deploy_limit=prior_deploy_limit,
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def get_workspace_session(
        ctx: Context[ServerSession, AppContext],
    ) -> SessionState:
        """Get active property/library hints stored for this API session."""
        try:
            return await ctx.request_context.lifespan_context.api.get_session()
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def set_workspace_session(
        ctx: Context[ServerSession, AppContext],
        active_property_id: Annotated[str | None, Field(description="Property ID to remember.")] = None,
        active_property_name: Annotated[str | None, Field(description="Property display name.")] = None,
        active_library_id: Annotated[str | None, Field(description="Library ID to remember.")] = None,
        active_library_name: Annotated[str | None, Field(description="Library display name.")] = None,
    ) -> SessionState:
        """Store active property/library after the user explicitly chooses one."""
        try:
            return await ctx.request_context.lifespan_context.api.update_session(
                active_property_id=active_property_id,
                active_property_name=active_property_name,
                active_library_id=active_library_id,
                active_library_name=active_library_name,
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def clear_workspace_session(
        ctx: Context[ServerSession, AppContext],
    ) -> dict[str, bool]:
        """Clear stored property/library workspace hints without disconnecting Adobe auth."""
        try:
            return await ctx.request_context.lifespan_context.api.clear_session()
        except ApiError as error:
            raise to_tool_error(error) from error
