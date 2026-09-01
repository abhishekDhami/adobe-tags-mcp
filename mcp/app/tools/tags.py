from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from pydantic import Field

from app.clients import ApiError, to_tool_error
from app.context import AppContext
from app.models.tags import (
    AuthStatusResult,
    PaginatedResources,
    PaginatedRules,
    ResourceDetail,
    RevisionHistoryResult,
    RuleDetail,
)


def register_tags_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_adobe_auth_status(
        ctx: Context[ServerSession, AppContext],
    ) -> AuthStatusResult:
        """Return Adobe connection status for the local API session.

        Use before other Tags tools to confirm Adobe authentication mode and
        whether the user or service account is connected.
        """
        try:
            return await ctx.request_context.lifespan_context.api.get_auth_status()
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def list_properties(
        ctx: Context[ServerSession, AppContext],
        page: Annotated[int, Field(description="1-based page number.", ge=1)] = 1,
        page_size: Annotated[
            int, Field(description="Items per page. Uses API default when 0.", ge=0, le=100)
        ] = 0,
    ) -> PaginatedResources:
        """List Adobe Tags properties available to the connected Adobe identity.

        Returns summary rows only. Use this first to choose a property_id for
        other tools.
        """
        try:
            return await ctx.request_context.lifespan_context.api.list_properties(
                page=page, page_size=page_size
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def list_rules(
        ctx: Context[ServerSession, AppContext],
        property_id: Annotated[str, Field(description="Adobe Tags property ID (PR...).")],
        page: Annotated[int, Field(ge=1)] = 1,
        page_size: Annotated[int, Field(ge=0, le=100)] = 0,
        search: Annotated[str | None, Field(description="Optional rule name filter.")] = None,
    ) -> PaginatedRules:
        """List rules for a property as summary rows.

        Do not fetch every rule in detail. Call get_rule only for rules the user
        wants to inspect.
        """
        try:
            return await ctx.request_context.lifespan_context.api.list_rules(
                property_id, page=page, page_size=page_size, search=search
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def get_rule(
        ctx: Context[ServerSession, AppContext],
        rule_id: Annotated[str, Field(description="Adobe Tags rule ID.")],
        depth: Annotated[
            str,
            Field(
                description="View depth: index, detail, context (default), or full.",
            ),
        ] = "context",
        include_code: Annotated[
            bool, Field(description="Include full custom code when true.")
        ] = False,
        include_raw_settings: Annotated[
            bool, Field(description="Include raw settings JSON strings when true.")
        ] = False,
    ) -> RuleDetail:
        """Get one rule as an AI-native view with structured logic (events/conditions/actions).

        Default depth is context: audit fields plus hydrated extension names and parsed
        settings summaries. Includes a versions block (latest vs live, publishState).
        Use list_rule_revisions for important revision history (pass view=full for all).
        """
        try:
            return await ctx.request_context.lifespan_context.api.get_rule(
                rule_id,
                depth=depth,
                include_code=include_code,
                include_raw_settings=include_raw_settings,
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def list_rule_revisions(
        ctx: Context[ServerSession, AppContext],
        rule_id: Annotated[str, Field(description="Adobe Tags rule ID (head/working id from list_rules).")],
        view: Annotated[
            str,
            Field(
                description=(
                    "important (default): only revisions that are in a development library, "
                    "the head not in any development library, and/or published/live. "
                    "full: every revision (unimportant rows have important=false)."
                )
            ),
        ] = "important",
    ) -> RevisionHistoryResult:
        """List important revision snapshots for a rule (newest first). Pass view=full for all revisions.

        For latest vs live summary use get_rule — it includes a versions block.
        """
        try:
            return await ctx.request_context.lifespan_context.api.get_rule_versions(
                rule_id, view=view
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def list_data_elements(
        ctx: Context[ServerSession, AppContext],
        property_id: Annotated[str, Field(description="Adobe Tags property ID (PR...).")],
        page: Annotated[int, Field(ge=1)] = 1,
        page_size: Annotated[int, Field(ge=0, le=100)] = 0,
        search: Annotated[str | None, Field(description="Optional data element name filter.")] = None,
    ) -> PaginatedResources:
        """List data elements for a property as summary rows."""
        try:
            return await ctx.request_context.lifespan_context.api.list_data_elements(
                property_id, page=page, page_size=page_size, search=search
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def get_data_element(
        ctx: Context[ServerSession, AppContext],
        data_element_id: Annotated[str, Field(description="Adobe Tags data element ID.")],
        depth: Annotated[str, Field(description="View depth: index, detail (default), context, full.")] = "detail",
        include_code: Annotated[bool, Field(description="Include full custom code when true.")] = False,
        include_raw_settings: Annotated[
            bool, Field(description="Include raw settings JSON strings when true.")
        ] = False,
    ) -> ResourceDetail:
        """Get one data element as an AI-native view (no raw Adobe JSON)."""
        try:
            return await ctx.request_context.lifespan_context.api.get_data_element(
                data_element_id,
                depth=depth,
                include_code=include_code,
                include_raw_settings=include_raw_settings,
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def list_data_element_revisions(
        ctx: Context[ServerSession, AppContext],
        data_element_id: Annotated[str, Field(description="Adobe Tags data element ID.")],
        view: Annotated[
            str,
            Field(
                description=(
                    "important (default): only revisions in a development library, "
                    "head not in any development library, and/or published/live. "
                    "full: every revision."
                )
            ),
        ] = "important",
    ) -> RevisionHistoryResult:
        """List important revision snapshots for a data element. Pass view=full for all revisions."""
        try:
            return await ctx.request_context.lifespan_context.api.get_data_element_versions(
                data_element_id, view=view
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def list_extensions(
        ctx: Context[ServerSession, AppContext],
        property_id: Annotated[str, Field(description="Adobe Tags property ID (PR...).")],
        page: Annotated[int, Field(ge=1)] = 1,
        page_size: Annotated[int, Field(ge=0, le=100)] = 0,
    ) -> PaginatedResources:
        """List installed extensions for a property as summary rows."""
        try:
            return await ctx.request_context.lifespan_context.api.list_extensions(
                property_id, page=page, page_size=page_size
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def get_extension(
        ctx: Context[ServerSession, AppContext],
        extension_id: Annotated[str, Field(description="Adobe Tags extension ID.")],
        depth: Annotated[str, Field(description="View depth: index, detail (default), context, full.")] = "detail",
        include_raw_settings: Annotated[
            bool, Field(description="Include raw settings JSON strings when true.")
        ] = False,
    ) -> ResourceDetail:
        """Get one extension as an AI-native view (read-only)."""
        try:
            return await ctx.request_context.lifespan_context.api.get_extension(
                extension_id,
                depth=depth,
                include_raw_settings=include_raw_settings,
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def list_extension_revisions(
        ctx: Context[ServerSession, AppContext],
        extension_id: Annotated[str, Field(description="Adobe Tags extension ID.")],
        view: Annotated[
            str,
            Field(
                description=(
                    "important (default): only revisions in a development library, "
                    "head not in any development library, and/or published/live. "
                    "full: every revision."
                )
            ),
        ] = "important",
    ) -> RevisionHistoryResult:
        """List important revision snapshots for an extension. Pass view=full for all revisions."""
        try:
            return await ctx.request_context.lifespan_context.api.get_extension_versions(
                extension_id, view=view
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def search_tags_resources(
        ctx: Context[ServerSession, AppContext],
        query: Annotated[str, Field(description="Name search text.", min_length=1)],
        page: Annotated[int, Field(ge=1)] = 1,
        page_size: Annotated[int, Field(ge=0, le=100)] = 0,
        resource_types: Annotated[
            list[str] | None,
            Field(description="Optional Reactor resource types filter."),
        ] = None,
    ) -> PaginatedResources:
        """Search Adobe Tags resources by name across the current company."""
        try:
            return await ctx.request_context.lifespan_context.api.search_tags_resources(
                query, page=page, page_size=page_size, resource_types=resource_types
            )
        except ApiError as error:
            raise to_tool_error(error) from error
