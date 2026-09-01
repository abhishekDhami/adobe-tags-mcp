from __future__ import annotations

import pytest

from app.config import ConfigurationError, load_settings


API_ENV_NAMES = (
    "API_HOST",
    "API_PORT",
    "AUTH_ENABLED",
    "MCP_API_KEY",
    "ADOBE_AUTH_MODE",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in API_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_default_api_host_is_loopback() -> None:
    settings = load_settings()
    assert settings.api_host == "127.0.0.1"


def test_localhost_api_host_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_HOST", "localhost")
    settings = load_settings()
    assert settings.api_host == "localhost"


def test_non_loopback_api_host_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_HOST", "0.0.0.0")
    with pytest.raises(ConfigurationError, match="loopback host"):
        load_settings()
