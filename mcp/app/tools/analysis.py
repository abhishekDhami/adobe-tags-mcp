from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from pydantic import Field

from app.clients import ApiError, to_tool_error
from app.context import AppContext
from app.models.analysis import RuleDependenciesResult, UsageSearchResult


def register_analysis_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_rule_dependencies(
        ctx: Context[ServerSession, AppContext],
        rule_id: Annotated[str, Field(description="Adobe Tags rule ID (RL...).")],
        version_scope: Annotated[
            str,
            Field(
                description=(
                    "Which revision to scan: 'latest' (default, working copy) or "
                    "'live' (production revision). Live returns an empty graph if never published."
                ),
            ),
        ] = "latest",
    ) -> RuleDependenciesResult:
        """List data elements and extensions referenced by a rule's components.

        Detects %Data Element: Name% tokens and _satellite.getVar("Name") in custom code.
        Response always includes versionContext (publishState, scanned vs live revision).
        """
        try:
            return await ctx.request_context.lifespan_context.api.get_rule_dependencies(
                rule_id,
                version_scope=version_scope,
            )
        except ApiError as error:
            raise to_tool_error(error) from error

    @mcp.tool()
    async def find_usage(
        ctx: Context[ServerSession, AppContext],
        property_id: Annotated[str, Field(description="Adobe Tags property ID (PR...).")],
        query: Annotated[
            str,
            Field(
                description=(
                    "Arbitrary settings text (default freeText), or a data element name/id "
                    "when mode=dataElement."
                ),
                min_length=1,
            ),
        ],
        version_scope: Annotated[
            str,
            Field(
                description=(
                    "latest (default): working/saved revisions only. "
                    "live: published/production revisions. Always tell the user which was used."
                ),
            ),
        ] = "latest",
        mode: Annotated[
            str,
            Field(
                description=(
                    "freeText (default): search settings text (rules, DEs, extensions). "
                    "Use for unknown keywords. dataElement: resolve a known DE and find "
                    "token/getVar refs; if no DE matches, API auto-falls back to freeText."
                ),
            ),
        ] = "freeText",
        detail: Annotated[
            str,
            Field(
                description=(
                    "hits (default): fast high-level list (id/name/type) like Tags UI search. "
                    "For more on one hit, call get_rule / get_data_element / get_extension. "
                    "summary|components: slower enriched consumer aggregation."
                ),
            ),
        ] = "hits",
    ) -> UsageSearchResult:
        """Find where a string/data element is used on a property (where-is-this-used).

        Default is fast: freeText settings search, latest revisions, detail=hits.
        Pass mode=dataElement only when the user clearly means a known data element.
        Always tell the user the answer is based on latest or live.
        Do not pass detail=summary/components unless the user needs aggregated consumers.
        """
        try:
            return await ctx.request_context.lifespan_context.api.find_usage(
                property_id,
                query=query,
                version_scope=version_scope,
                mode=mode,
                detail=detail,
            )
        except ApiError as error:
            raise to_tool_error(error) from error
