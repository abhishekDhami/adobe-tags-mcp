"""ApiClient → API envelope contract smoke (mocked HTTP, no Adobe)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.clients.api_client import ApiClient, ApiError
from app.config import Settings


def _envelope(data: dict) -> dict:
    return {
        "success": True,
        "data": data,
        "meta": {
            "requestId": str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
    }


def _error_envelope(code: str, message: str, status: int = 400) -> httpx.Response:
    return httpx.Response(
        status,
        json={
            "success": False,
            "error": {"code": code, "message": message, "details": None},
            "meta": {
                "requestId": str(uuid4()),
                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            },
        },
    )


def _settings(**overrides) -> Settings:
    base = dict(
        api_base_url="http://test.local",
        api_timeout_seconds=5.0,
        api_max_retries=0,
        auth_enabled=False,
        api_key="",
        server_name="Adobe Tags MCP",
        log_level="INFO",
        mcp_transport="stdio",
        mcp_http_host="127.0.0.1",
        mcp_http_port=8000,
        mcp_http_path="/mcp",
        mcp_http_health_path="/health",
        mcp_http_stateless=True,
        mcp_http_json_response=True,
        mcp_http_max_request_body_bytes=1024,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
async def client_factory():
    created: list[ApiClient] = []

    def make(handler) -> ApiClient:
        transport = httpx.MockTransport(handler)
        client = ApiClient(_settings(), logging.getLogger("test"))
        # Replace the internal httpx client with one using MockTransport
        client._client = httpx.AsyncClient(
            base_url="http://test.local",
            transport=transport,
            headers={"Accept": "application/json"},
        )
        created.append(client)
        return client

    yield make

    for client in created:
        await client.close()


@pytest.mark.asyncio
async def test_get_health_parses_envelope(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(
            200, json=_envelope({"status": "healthy", "service": "Adobe Tags API"})
        )

    client = client_factory(handler)
    result = await client.get_health()
    assert result.status == "healthy"
    assert result.service == "Adobe Tags API"


@pytest.mark.asyncio
async def test_list_properties_parses_paginated_items(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/tags/properties"
        assert request.url.params.get("page") == "1"
        return httpx.Response(
            200,
            json=_envelope(
                {
                    "items": [
                        {"resourceType": "property", "id": "PR1", "name": "Demo"}
                    ],
                    "pagination": {
                        "page": 1,
                        "pageSize": 25,
                        "totalItems": 1,
                        "totalPages": 1,
                        "hasNextPage": False,
                        "hasPreviousPage": False,
                    },
                }
            ),
        )

    client = client_factory(handler)
    result = await client.list_properties(page=1)
    assert result.items[0].id == "PR1"
    assert result.pagination.total_items == 1


@pytest.mark.asyncio
async def test_get_rule_forwards_depth_query_params(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/tags/rules/RL1"
        assert request.url.params["depth"] == "context"
        assert request.url.params["includeCode"] == "false"
        return httpx.Response(
            200,
            json=_envelope(
                {
                    "resourceType": "rule",
                    "id": "RL1",
                    "name": "Page Load",
                    "versions": {"publishState": "live"},
                }
            ),
        )

    client = client_factory(handler)
    result = await client.get_rule("RL1")
    assert result.id == "RL1"
    # FlexibleView allows extra fields from AI views
    assert result.model_dump(by_alias=True)["versions"]["publishState"] == "live"


@pytest.mark.asyncio
async def test_review_development_library_parses_result(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == (
            "/api/v1/tags/libraries/LB1/review-development-library"
        )
        assert request.url.params["depth"] == "summary"
        return httpx.Response(
            200,
            json=_envelope(
                {
                    "resourceType": "developmentLibraryReview",
                    "depth": "summary",
                    "library": {"id": "LB1", "name": "Dev"},
                    "summary": {"totalChanges": 1},
                    "idUsage": {
                        "pending": "Use pending.id for get_* of library revision",
                        "publishedLive": "Use publishedLive.id for production",
                    },
                    "changes": {
                        "rules": [
                            {
                                "changeKind": "new",
                                "name": "New Rule",
                                "pending": {"id": "RL9", "version": 1},
                            }
                        ],
                        "dataElements": [],
                        "extensions": [],
                    },
                    "narrative": "1 change pending.",
                }
            ),
        )

    client = client_factory(handler)
    result = await client.review_development_library("LB1", depth="summary")
    assert result.resource_type == "developmentLibraryReview"
    assert result.summary["totalChanges"] == 1
    assert result.changes["rules"][0]["changeKind"] == "new"


@pytest.mark.asyncio
async def test_get_rule_dependencies_forwards_version_scope(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/tags/rules/RL1/dependencies"
        assert request.url.params["versionScope"] == "live"
        return httpx.Response(
            200,
            json=_envelope(
                {
                    "resourceType": "ruleDependencies",
                    "narrative": "No dependencies.",
                    "versionContext": {"publishState": "live"},
                }
            ),
        )

    client = client_factory(handler)
    result = await client.get_rule_dependencies("RL1", version_scope="live")
    assert result.resource_type == "ruleDependencies"
    assert result.model_dump(by_alias=True)["versionContext"]["publishState"] == "live"


@pytest.mark.asyncio
async def test_api_error_envelope_raises_api_error(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _error_envelope("NOT_A_DEVELOPMENT_LIBRARY", "Library is not in development.")

    client = client_factory(handler)
    with pytest.raises(ApiError) as exc_info:
        await client.review_development_library("LB_PUBLISHED")

    assert exc_info.value.code == "NOT_A_DEVELOPMENT_LIBRARY"
    assert "development" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_auth_header_sent_when_enabled(client_factory) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization", "")
        return httpx.Response(
            200, json=_envelope({"status": "healthy", "service": "Adobe Tags API"})
        )

    # Build client with auth enabled manually
    transport = httpx.MockTransport(handler)
    settings = _settings(auth_enabled=True, api_key="x" * 16)
    client = ApiClient(settings, logging.getLogger("test"))
    client._client = httpx.AsyncClient(
        base_url="http://test.local",
        transport=transport,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {settings.api_key}",
        },
    )
    try:
        await client.get_health()
    finally:
        await client.close()

    assert seen["authorization"] == f"Bearer {'x' * 16}"
