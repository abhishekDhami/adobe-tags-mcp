from __future__ import annotations

import pytest

from app.config import ConfigurationError, load_settings


MCP_ENV_NAMES = (
    "AUTH_ENABLED",
    "MCP_API_KEY",
    "API_BASE_URL",
    "API_TIMEOUT_SECONDS",
    "API_MAX_RETRIES",
    "MCP_SERVER_NAME",
    "LOG_LEVEL",
    "MCP_TRANSPORT",
    "MCP_HTTP_HOST",
    "MCP_HTTP_PORT",
    "MCP_HTTP_PATH",
    "MCP_HTTP_HEALTH_PATH",
    "MCP_HTTP_STATELESS",
    "MCP_HTTP_JSON_RESPONSE",
    "MCP_HTTP_MAX_REQUEST_BODY_BYTES",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in MCP_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_stdio_is_the_default_transport() -> None:
    settings = load_settings()

    assert settings.mcp_transport == "stdio"
    assert settings.mcp_http_url == "http://127.0.0.1:8000/mcp"
    assert settings.mcp_http_stateless is True
    assert settings.mcp_http_json_response is True


def test_streamable_http_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("MCP_HTTP_PORT", "9000")
    monkeypatch.setenv("MCP_HTTP_PATH", "/agent/mcp")
    monkeypatch.setenv("MCP_HTTP_HEALTH_PATH", "/agent/health")
    monkeypatch.setenv("MCP_HTTP_JSON_RESPONSE", "false")

    settings = load_settings()

    assert settings.mcp_transport == "streamable-http"
    assert settings.mcp_http_url == "http://127.0.0.1:9000/agent/mcp"
    assert settings.mcp_http_health_url == "http://127.0.0.1:9000/agent/health"
    assert settings.mcp_http_json_response is False


def test_remote_streamable_http_binding_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("MCP_HTTP_HOST", "0.0.0.0")

    with pytest.raises(ConfigurationError, match="loopback host"):
        load_settings()


def test_stdio_ignores_non_loopback_http_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")
    monkeypatch.setenv("MCP_HTTP_HOST", "0.0.0.0")

    settings = load_settings()

    assert settings.mcp_transport == "stdio"
    assert settings.mcp_http_host == "0.0.0.0"


def test_mcp_and_health_paths_cannot_collide(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_HTTP_PATH", "/mcp")
    monkeypatch.setenv("MCP_HTTP_HEALTH_PATH", "/mcp")

    with pytest.raises(ConfigurationError, match="must be different"):
        load_settings()
