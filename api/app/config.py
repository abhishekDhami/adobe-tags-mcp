from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
API_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(API_PACKAGE_ROOT / ".env")

AdobeAuthMode = Literal["user_oauth", "server_to_server"]


class ConfigurationError(RuntimeError):
    """Raised when required API configuration is invalid."""


def _read_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name, str(default)).strip().lower()
    if raw_value not in {"true", "false"}:
        raise ConfigurationError(f"{name} must be either 'true' or 'false'.")
    return raw_value == "true"


def _read_port(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if value < 1 or value > 65535:
        raise ConfigurationError(f"{name} must be between 1 and 65535.")
    return value


def _read_auth_mode() -> AdobeAuthMode:
    value = os.getenv("ADOBE_AUTH_MODE", "server_to_server").strip().lower()
    if value not in {"user_oauth", "server_to_server"}:
        raise ConfigurationError(
            "ADOBE_AUTH_MODE must be 'user_oauth' or 'server_to_server'."
        )
    return value  # type: ignore[return-value]


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class Settings:
    api_host: str
    api_port: int
    api_version: str
    environment: str
    log_level: str
    auth_enabled: bool
    mcp_api_key: str
    service_name: str
    adobe_auth_mode: AdobeAuthMode
    adobe_client_id: str
    adobe_client_secret: str
    adobe_org_id: str
    adobe_scopes: str
    adobe_ims_token_url: str
    adobe_ims_authorize_url: str
    adobe_oauth_redirect_uri: str
    reactor_base_url: str
    data_dir: Path
    vault_key: str
    default_page_size: int
    max_page_size: int

    @property
    def bind_url(self) -> str:
        return f"http://{self.api_host}:{self.api_port}"


def load_settings() -> Settings:
    auth_enabled = _read_bool("AUTH_ENABLED", False)
    mcp_api_key = os.getenv("MCP_API_KEY", "").strip()
    if auth_enabled and len(mcp_api_key) < 16:
        raise ConfigurationError(
            "MCP_API_KEY must contain at least 16 characters when AUTH_ENABLED=true."
        )

    api_host = os.getenv("API_HOST", "127.0.0.1").strip()
    if not api_host:
        raise ConfigurationError("API_HOST cannot be empty.")
    if not _is_loopback_host(api_host):
        raise ConfigurationError(
            "API_HOST must be a loopback host (127.0.0.1, ::1, or localhost). "
            "This API is intentionally local-only; do not bind to 0.0.0.0 or a public interface."
        )

    data_dir = REPOSITORY_ROOT / os.getenv("DATA_DIR", "data").strip()
    default_page_size = int(os.getenv("DEFAULT_PAGE_SIZE", "25"))
    max_page_size = int(os.getenv("MAX_PAGE_SIZE", "50"))
    if default_page_size < 1 or max_page_size < default_page_size:
        raise ConfigurationError("Invalid DEFAULT_PAGE_SIZE or MAX_PAGE_SIZE.")

    return Settings(
        api_host=api_host,
        api_port=_read_port("API_PORT", 3000),
        api_version=os.getenv("API_VERSION", "0.1.0").strip(),
        environment=os.getenv("API_ENV", "development").strip(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        auth_enabled=auth_enabled,
        mcp_api_key=mcp_api_key,
        service_name=os.getenv("API_SERVICE_NAME", "Adobe Tags API").strip(),
        adobe_auth_mode=_read_auth_mode(),
        adobe_client_id=os.getenv("ADOBE_CLIENT_ID", "").strip(),
        adobe_client_secret=os.getenv("ADOBE_CLIENT_SECRET", "").strip(),
        adobe_org_id=os.getenv("ADOBE_ORG_ID", "").strip(),
        adobe_scopes=os.getenv(
            "ADOBE_SCOPES",
            "openid,AdobeID,read_organizations,additional_info.projectedProductContext",
        ).strip(),
        adobe_ims_token_url=os.getenv(
            "ADOBE_IMS_TOKEN_URL", "https://ims-na1.adobelogin.com/ims/token/v3"
        ).strip(),
        adobe_ims_authorize_url=os.getenv(
            "ADOBE_IMS_AUTHORIZE_URL",
            "https://ims-na1.adobelogin.com/ims/authorize/v2",
        ).strip(),
        adobe_oauth_redirect_uri=os.getenv(
            "ADOBE_OAUTH_REDIRECT_URI", "http://127.0.0.1:3000/auth/adobe/callback"
        ).strip(),
        reactor_base_url=os.getenv("REACTOR_BASE_URL", "https://reactor.adobe.io").strip().rstrip("/"),
        data_dir=data_dir,
        vault_key=os.getenv("VAULT_KEY", "").strip(),
        default_page_size=default_page_size,
        max_page_size=max_page_size,
    )
