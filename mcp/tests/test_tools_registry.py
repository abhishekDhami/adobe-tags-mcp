from __future__ import annotations

import pytest

from app.config import load_settings
from app.server import create_server


# Keep in sync with PROJECT_CONTEXT.md "MCP tools (current)".
EXPECTED_TOOLS = frozenset(
    {
        # System
        "get_system_health",
        "get_system_status",
        # Discovery
        "get_adobe_auth_status",
        "list_properties",
        "list_rules",
        "get_rule",
        "list_data_elements",
        "get_data_element",
        "list_extensions",
        "get_extension",
        "search_tags_resources",
        # Versions
        "list_rule_revisions",
        "list_data_element_revisions",
        "list_extension_revisions",
        # Libraries
        "list_environments",
        "list_published_libraries",
        "get_development_library",
        "get_library",
        "list_library_resources",
        "review_development_library",
        "get_property_activity",
        # Session
        "get_workspace_session",
        "set_workspace_session",
        "clear_workspace_session",
        # Analysis
        "get_rule_dependencies",
        "find_usage",
    }
)


@pytest.fixture
def mcp_server(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "MCP_TRANSPORT",
        "MCP_HTTP_HOST",
        "MCP_HTTP_PORT",
        "AUTH_ENABLED",
        "MCP_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    return create_server(load_settings())


@pytest.mark.asyncio
async def test_all_expected_tools_are_registered(mcp_server) -> None:
    tools = await mcp_server.list_tools()
    names = {tool.name for tool in tools}

    missing = EXPECTED_TOOLS - names
    unexpected = names - EXPECTED_TOOLS

    assert not missing, f"Missing MCP tools: {sorted(missing)}"
    assert not unexpected, f"Unexpected MCP tools: {sorted(unexpected)}"


@pytest.mark.asyncio
async def test_tool_descriptions_are_non_empty(mcp_server) -> None:
    tools = await mcp_server.list_tools()
    empty = [tool.name for tool in tools if not (tool.description or "").strip()]
    assert not empty, f"Tools missing descriptions: {empty}"
