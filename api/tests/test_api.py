from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adobe.reactor_client import ReadOnlyReactorClient, ReadOnlyViolationError
from app.config import Settings
from app.main import create_app


def make_settings(**overrides) -> Settings:
    base = Settings(
        api_host="127.0.0.1",
        api_port=3000,
        api_version="0.1.0-test",
        environment="test",
        log_level="INFO",
        auth_enabled=False,
        mcp_api_key="",
        service_name="Adobe Tags API Test",
        adobe_auth_mode="server_to_server",
        adobe_client_id="",
        adobe_client_secret="",
        adobe_org_id="",
        adobe_scopes="openid",
        adobe_ims_token_url="https://ims-na1.adobelogin.com/ims/token/v3",
        adobe_ims_authorize_url="https://ims-na1.adobelogin.com/ims/authorize/v2",
        adobe_oauth_redirect_uri="http://127.0.0.1:3000/auth/adobe/callback",
        reactor_base_url="https://reactor.adobe.io",
        data_dir=Path(tempfile.gettempdir()) / "adobe-tags-test",
        vault_key="",
        default_page_size=25,
        max_page_size=50,
    )
    return replace(base, **overrides)


@pytest.fixture
def client() -> TestClient:
    settings = make_settings()
    return TestClient(create_app(settings))


def test_health_returns_envelope(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "healthy"


def test_auth_status_when_not_configured(client: TestClient) -> None:
    response = client.get("/api/v1/auth/status")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["connected"] is False
    assert body["mode"] == "server_to_server"


def test_auth_required_when_enabled() -> None:
    settings = make_settings(auth_enabled=True, mcp_api_key="test-secret-key-12345")
    client = TestClient(create_app(settings))

    response = client.get("/api/v1/tags/properties")
    assert response.status_code == 401

    response = client.get(
        "/api/v1/tags/properties",
        headers={"Authorization": "Bearer test-secret-key-12345"},
    )
    assert response.status_code in {200, 401, 400, 502}


def test_readonly_client_blocks_mutations() -> None:
    class DummyAuth:
        mode = "server_to_server"

        async def get_headers(self):
            raise AssertionError("should not be called")

    client = ReadOnlyReactorClient(DummyAuth(), "https://reactor.adobe.io")
    with pytest.raises(ReadOnlyViolationError):
        import asyncio

        asyncio.run(client.request("POST", "/properties/PR/rules", json={"data": {}}))
