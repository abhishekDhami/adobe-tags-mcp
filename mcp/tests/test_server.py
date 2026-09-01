from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.config import ConfigurationError, load_settings
from app.server import RequestBodyLimitMiddleware, create_server, main, run


def test_server_receives_streamable_http_settings(monkeypatch) -> None:
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("MCP_HTTP_PORT", "9100")
    monkeypatch.setenv("MCP_HTTP_PATH", "/custom-mcp")
    monkeypatch.setenv("MCP_HTTP_STATELESS", "true")
    monkeypatch.setenv("MCP_HTTP_JSON_RESPONSE", "false")
    settings = load_settings()

    server = create_server(settings)

    assert server.settings.host == "127.0.0.1"
    assert server.settings.port == 9100
    assert server.settings.streamable_http_path == "/custom-mcp"
    assert server.settings.stateless_http is True
    assert server.settings.json_response is False


def test_streamable_http_health_route(monkeypatch) -> None:
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")
    settings = load_settings()
    server = create_server(settings)

    with TestClient(server.streamable_http_app()) as client:
        response = client.get(settings.mcp_http_health_path)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["mcpEndpoint"] == settings.mcp_http_path


def test_run_dispatches_stdio(monkeypatch) -> None:
    settings = replace(load_settings(), mcp_transport="stdio")
    fake_server = Mock()
    monkeypatch.setattr("app.server.create_server", lambda _settings, logger: fake_server)

    run(settings)

    fake_server.run.assert_called_once_with(transport="stdio")


def test_run_dispatches_streamable_http(monkeypatch) -> None:
    settings = replace(load_settings(), mcp_transport="streamable-http")
    fake_server = Mock()
    calls = []
    monkeypatch.setattr("app.server.create_server", lambda _settings, logger: fake_server)
    monkeypatch.setattr(
        "app.server.anyio.run",
        lambda function, *args: calls.append((function, args)),
    )

    run(settings)

    fake_server.run.assert_not_called()
    assert calls[0][1] == (fake_server, settings)


def test_cli_transport_overrides_environment(monkeypatch) -> None:
    settings = load_settings()
    captured = []
    monkeypatch.setattr("app.server.load_settings", lambda: settings)
    monkeypatch.setattr("app.server.run", lambda value: captured.append(value))

    main(["--transport", "streamable-http"])

    assert captured[0].mcp_transport == "streamable-http"


def test_cli_override_cannot_bypass_loopback_guard(monkeypatch) -> None:
    settings = replace(load_settings(), mcp_http_host="0.0.0.0")
    monkeypatch.setattr("app.server.load_settings", lambda: settings)

    with pytest.raises(ConfigurationError, match="loopback host"):
        main(["--transport", "streamable-http"])


def test_request_body_limit_rejects_declared_oversized_body() -> None:
    async def endpoint(_request):
        return JSONResponse({"status": "ok"})

    app = RequestBodyLimitMiddleware(
        Starlette(routes=[Route("/mcp", endpoint, methods=["POST"])]),
        max_bytes=10,
    )

    with TestClient(app) as client:
        response = client.post("/mcp", content=b"01234567890")

    assert response.status_code == 413
    assert response.json() == {"error": "request_body_too_large"}
