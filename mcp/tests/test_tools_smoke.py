"""MCP → mocked ApiClient smoke: each tool reaches the API client correctly."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext

from app.config import load_settings
from app.context import AppContext
from app.models.analysis import RuleDependenciesResult, UsageSearchResult
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
from app.models.tags import (
    AuthStatusResult,
    PaginatedResources,
    PaginatedRules,
    ResourceDetail,
    RevisionHistoryResult,
    RuleDetail,
)
from app.models.tools import HealthResult, SystemStatusResult
from app.server import create_server


def _pagination() -> dict:
    return {
        "page": 1,
        "pageSize": 25,
        "totalItems": 1,
        "totalPages": 1,
        "hasNextPage": False,
        "hasPreviousPage": False,
    }


@pytest.fixture
def mcp_server(monkeypatch: pytest.MonkeyPatch):
    for name in ("MCP_TRANSPORT", "AUTH_ENABLED", "MCP_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return create_server(load_settings())


@pytest.fixture
def api_mock() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
async def with_api_context(mcp_server, api_mock):
    """Install a request context so tools can resolve lifespan_context.api."""
    ctx = RequestContext(
        request_id="mcp-smoke",
        meta=None,
        session=Mock(),
        lifespan_context=AppContext(api=api_mock),
    )
    token = request_ctx.set(ctx)
    try:
        yield api_mock
    finally:
        request_ctx.reset(token)


async def _call(server, name: str, arguments: dict | None = None):
    result = await server.call_tool(name, arguments or {})
    # FastMCP returns (content_blocks, structured) when the tool has a Pydantic return type.
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
        return result[1]
    raise AssertionError(
        f"Tool {name!r} did not return structured output; got {type(result).__name__}: {result!r}"
    )


@pytest.mark.asyncio
async def test_system_tools_smoke(mcp_server, with_api_context) -> None:
    api = with_api_context
    api.get_health.return_value = HealthResult(status="healthy", service="Adobe Tags API")
    api.get_status.return_value = SystemStatusResult(
        status="ok",
        service="Adobe Tags API",
        version="0.1.0",
        environment="development",
        uptimeSeconds=1,
        currentTime="2026-08-05T00:00:00Z",
        authenticationEnabled=False,
    )

    health = await _call(mcp_server, "get_system_health")
    status = await _call(mcp_server, "get_system_status")

    assert health["status"] == "healthy"
    assert status["status"] == "ok"
    api.get_health.assert_awaited_once()
    api.get_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_discovery_tools_smoke(mcp_server, with_api_context) -> None:
    api = with_api_context
    api.get_auth_status.return_value = AuthStatusResult(
        connected=True, mode="server_to_server", message="Connected"
    )
    api.list_properties.return_value = PaginatedResources(
        items=[{"resourceType": "property", "id": "PR1", "name": "Demo"}],
        pagination=_pagination(),
    )
    api.list_rules.return_value = PaginatedRules(
        items=[{"resourceType": "rule", "id": "RL1", "name": "Page Load"}],
        pagination=_pagination(),
    )
    api.get_rule.return_value = RuleDetail(resourceType="rule", id="RL1", name="Page Load")
    api.get_rule_versions.return_value = RevisionHistoryResult(
        resourceType="revisionHistory", resourceKind="rule", headId="RL1", name="Page Load"
    )
    api.list_data_elements.return_value = PaginatedResources(items=[], pagination=_pagination())
    api.get_data_element.return_value = ResourceDetail(
        resourceType="dataElement", id="DE1", name="Page Name"
    )
    api.get_data_element_versions.return_value = RevisionHistoryResult(
        resourceType="revisionHistory", resourceKind="dataElement", headId="DE1"
    )
    api.list_extensions.return_value = PaginatedResources(items=[], pagination=_pagination())
    api.get_extension.return_value = ResourceDetail(
        resourceType="extension", id="EX1", name="Core"
    )
    api.get_extension_versions.return_value = RevisionHistoryResult(
        resourceType="revisionHistory", resourceKind="extension", headId="EX1"
    )
    api.search_tags_resources.return_value = PaginatedResources(items=[], pagination=_pagination())

    auth = await _call(mcp_server, "get_adobe_auth_status")
    props = await _call(mcp_server, "list_properties", {"page": 1})
    rules = await _call(mcp_server, "list_rules", {"property_id": "PR1"})
    rule = await _call(mcp_server, "get_rule", {"rule_id": "RL1"})
    rule_revs = await _call(mcp_server, "list_rule_revisions", {"rule_id": "RL1"})
    des = await _call(mcp_server, "list_data_elements", {"property_id": "PR1"})
    de = await _call(mcp_server, "get_data_element", {"data_element_id": "DE1"})
    de_revs = await _call(mcp_server, "list_data_element_revisions", {"data_element_id": "DE1"})
    exts = await _call(mcp_server, "list_extensions", {"property_id": "PR1"})
    ext = await _call(mcp_server, "get_extension", {"extension_id": "EX1"})
    ext_revs = await _call(mcp_server, "list_extension_revisions", {"extension_id": "EX1"})
    search = await _call(mcp_server, "search_tags_resources", {"query": "page"})

    assert auth["connected"] is True
    assert props["items"][0]["id"] == "PR1"
    assert rules["items"][0]["id"] == "RL1"
    assert rule["id"] == "RL1"
    assert rule_revs["resourceKind"] == "rule"
    assert des["pagination"]["page"] == 1
    assert de["id"] == "DE1"
    assert de_revs["headId"] == "DE1"
    assert exts["items"] == []
    assert ext["id"] == "EX1"
    assert ext_revs["resourceKind"] == "extension"
    assert search["items"] == []

    api.list_rules.assert_awaited_once()
    assert api.list_rules.await_args.args[0] == "PR1"
    api.get_rule.assert_awaited_once()
    api.search_tags_resources.assert_awaited_once()


@pytest.mark.asyncio
async def test_library_and_analysis_tools_smoke(mcp_server, with_api_context) -> None:
    api = with_api_context
    api.list_environments.return_value = EnvironmentListResult(items=[], totalCount=0)
    api.list_published_libraries.return_value = PaginatedLibraries(
        items=[], pagination=_pagination()
    )
    api.get_development_library.return_value = DevLibraryCandidateResult(
        status="resolved",
        library={"resourceType": "library", "id": "LB1", "name": "Dev", "state": "development"},
        message="Resolved",
    )
    api.get_library.return_value = LibraryDetail(
        resourceType="library", id="LB1", name="Dev", state="development"
    )
    api.list_library_resources.return_value = LibraryResourcesResult(
        libraryId="LB1", resourceType="all", items=[], totalCount=0
    )
    api.review_development_library.return_value = DevelopmentLibraryReviewResult(
        resourceType="developmentLibraryReview",
        depth="summary",
        library={"id": "LB1", "name": "Dev"},
        summary={"totalChanges": 0},
        changes={"rules": [], "dataElements": [], "extensions": []},
        narrative="No pending changes.",
    )
    api.get_session.return_value = SessionState()
    api.update_session.return_value = SessionState(activePropertyId="PR1")
    api.clear_session.return_value = {"cleared": True}
    api.get_rule_dependencies.return_value = RuleDependenciesResult(
        resourceType="ruleDependencies", narrative="No dependencies."
    )
    api.find_usage.return_value = UsageSearchResult(
        resourceType="usageSearch",
        propertyId="PR1",
        query="Page Name",
        versionScope="latest",
        status="ok",
        detail="hits",
        narrative="Based on latest saved (working) revisions. High-level search found 0 hit(s).",
    )
    api.get_property_activity.return_value = PropertyActivityResult(
        resourceType="propertyActivity",
        propertyId="PR1",
        focus="all",
        narrative="No published deployments in window.",
        deployments={"source": "priorToWindow", "inWindow": [], "priorToWindow": []},
        edits={"inWindow": []},
    )

    envs = await _call(mcp_server, "list_environments", {"property_id": "PR1"})
    pubs = await _call(mcp_server, "list_published_libraries", {"property_id": "PR1"})
    dev = await _call(mcp_server, "get_development_library", {"property_id": "PR1"})
    lib = await _call(mcp_server, "get_library", {"library_id": "LB1"})
    resources = await _call(mcp_server, "list_library_resources", {"library_id": "LB1"})
    review = await _call(
        mcp_server, "review_development_library", {"library_id": "LB1", "depth": "summary"}
    )
    activity = await _call(
        mcp_server,
        "get_property_activity",
        {
            "property_id": "PR1",
            "from_date": "2025-03-01",
            "to_date": "2025-03-31",
            "focus": "all",
        },
    )
    session = await _call(mcp_server, "get_workspace_session")
    updated = await _call(
        mcp_server, "set_workspace_session", {"active_property_id": "PR1"}
    )
    cleared = await _call(mcp_server, "clear_workspace_session")
    deps = await _call(
        mcp_server, "get_rule_dependencies", {"rule_id": "RL1", "version_scope": "live"}
    )
    usage = await _call(
        mcp_server,
        "find_usage",
        {
            "property_id": "PR1",
            "query": "Page Name",
        },
    )

    assert envs["totalCount"] == 0
    assert pubs["items"] == []
    assert dev["status"] == "resolved"
    assert lib["id"] == "LB1"
    assert resources["libraryId"] == "LB1"
    assert review["resourceType"] == "developmentLibraryReview"
    assert activity["resourceType"] == "propertyActivity"
    assert session.get("activePropertyId") is None
    assert updated["activePropertyId"] == "PR1"
    assert cleared["cleared"] is True
    assert deps["resourceType"] == "ruleDependencies"
    assert usage["resourceType"] == "usageSearch"
    assert usage["versionScope"] == "latest"

    api.review_development_library.assert_awaited_once_with("LB1", depth="summary")
    api.get_rule_dependencies.assert_awaited_once_with("RL1", version_scope="live")
    api.find_usage.assert_awaited_once_with(
        "PR1",
        query="Page Name",
        version_scope="latest",
        mode="freeText",
        detail="hits",
    )
    api.get_property_activity.assert_awaited_once()
