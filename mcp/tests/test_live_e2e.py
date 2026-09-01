"""
Optional live smoke: MCP ApiClient → running local API → Adobe.

Skipped by default. Enable with:

  set RUN_LIVE_MCP_E2E=1
  (API must already be running at API_BASE_URL, Adobe auth connected)

Windows:
  $env:RUN_LIVE_MCP_E2E=1
  .\\.venv\\Scripts\\python.exe -m pytest -q mcp\\tests\\test_live_e2e.py
"""

from __future__ import annotations

import logging
import os

import httpx
import pytest

from app.clients.api_client import ApiClient, ApiError
from app.config import load_settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MCP_E2E", "").strip().lower() not in {"1", "true", "yes"},
    reason="Set RUN_LIVE_MCP_E2E=1 with a running API + Adobe session to run live smoke.",
)


@pytest.fixture
async def live_client():
    settings = load_settings()
    client = ApiClient(settings, logging.getLogger("live-e2e"))
    try:
        yield client
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_live_api_reachable(live_client: ApiClient) -> None:
    health = await live_client.get_health()
    assert health.status == "healthy"


@pytest.mark.asyncio
async def test_live_adobe_auth_connected(live_client: ApiClient) -> None:
    status = await live_client.get_auth_status()
    assert status.connected is True, status.message


@pytest.mark.asyncio
async def test_live_list_properties_smoke(live_client: ApiClient) -> None:
    result = await live_client.list_properties(page=1, page_size=5)
    assert result.pagination.page == 1
    # Org may have zero properties; still a valid curated response
    assert isinstance(result.items, list)


@pytest.mark.asyncio
async def test_live_discovery_chain_when_property_exists(live_client: ApiClient) -> None:
    props = await live_client.list_properties(page=1, page_size=1)
    if not props.items:
        pytest.skip("No Adobe properties available for discovery chain smoke.")

    property_id = props.items[0].id
    assert property_id

    rules = await live_client.list_rules(property_id, page=1, page_size=1)
    assert rules.pagination.page == 1

    envs = await live_client.list_environments(property_id)
    assert envs.total_count >= 0

    try:
        await live_client.get_development_library(property_id)
    except ApiError as error:
        # Ambiguous/empty is still a successful API contract; transport failures are not.
        if error.code == "API_UNAVAILABLE":
            raise

    if rules.items:
        rule_id = rules.items[0].id
        assert rule_id
        detail = await live_client.get_rule(rule_id, depth="context")
        assert detail.id == rule_id
        dumped = detail.model_dump(by_alias=True)
        assert "versions" in dumped or detail.resource_type == "rule"

        history = await live_client.get_rule_versions(rule_id)
        assert history.resource_type == "revisionHistory" or history.head_id

        deps = await live_client.get_rule_dependencies(rule_id, version_scope="latest")
        assert deps.resource_type == "ruleDependencies" or deps.narrative is not None


@pytest.mark.asyncio
async def test_live_process_health_via_httpx() -> None:
    """Sanity that API_BASE_URL responds before client parsing."""
    settings = load_settings()
    async with httpx.AsyncClient(base_url=settings.api_base_url, timeout=10.0) as http:
        response = await http.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "healthy"
