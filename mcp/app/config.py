from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlsplit

from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MCP_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(MCP_PACKAGE_ROOT / ".env")

McpTransport = Literal["stdio", "streamable-http"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class ConfigurationError(RuntimeError):
    """Raised when required MCP server configuration is invalid."""


def _read_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name, str(default)).strip().lower()
    if raw_value not in {"true", "false"}:
        raise ConfigurationError(f"{name} must be either 'true' or 'false'.")
    return raw_value == "true"


def _read_positive_float(name: str, default: float) -> float:
    raw_value = os.getenv(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero.")
    return value


def _read_non_negative_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if value < 0:
        raise ConfigurationError(f"{name} cannot be negative.")
    return value


def _read_positive_int(name: str, default: int) -> int:
    value = _read_non_negative_int(name, default)
    if value == 0:
        raise ConfigurationError(f"{name} must be greater than zero.")
    return value


def _read_port(name: str, default: int) -> int:
    value = _read_positive_int(name, default)
    if value > 65535:
        raise ConfigurationError(f"{name} must be between 1 and 65535.")
    return value


def _read_transport() -> McpTransport:
    value = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()
    if value not in {"stdio", "streamable-http"}:
        raise ConfigurationError(
            "MCP_TRANSPORT must be either 'stdio' or 'streamable-http'."
        )
    return cast(McpTransport, value)


def _read_log_level() -> LogLevel:
    value = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if value not in allowed_levels:
        raise ConfigurationError(
            "LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL."
        )
    return cast(LogLevel, value)


def _read_http_path(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    if not value.startswith("/"):
        raise ConfigurationError(f"{name} must start with '/'.")
    if any(character.isspace() for character in value) or "?" in value or "#" in value:
        raise ConfigurationError(
            f"{name} must be a URL path without whitespace, a query string, or a fragment."
        )
    return value


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_runtime_settings(settings: "Settings") -> None:
    """Apply transport-specific safety checks after environment or CLI overrides."""
    if settings.mcp_transport == "streamable-http" and not _is_loopback_host(
        settings.mcp_http_host
    ):
        raise ConfigurationError(
            "MCP_HTTP_HOST must be a loopback host (127.0.0.1, ::1, or localhost). "
            "This starter intentionally prevents unauthenticated remote exposure."
        )


@dataclass(frozen=True, slots=True)
class Settings:
    api_base_url: str
    api_timeout_seconds: float
    api_max_retries: int
    auth_enabled: bool
    api_key: str
    server_name: str
    log_level: LogLevel
    mcp_transport: McpTransport
    mcp_http_host: str
    mcp_http_port: int
    mcp_http_path: str
    mcp_http_health_path: str
    mcp_http_stateless: bool
    mcp_http_json_response: bool
    mcp_http_max_request_body_bytes: int

    @property
    def mcp_http_url(self) -> str:
        """Return the local Streamable HTTP MCP endpoint URL."""
        host = f"[{self.mcp_http_host}]" if ":" in self.mcp_http_host else self.mcp_http_host
        return f"http://{host}:{self.mcp_http_port}{self.mcp_http_path}"

    @property
    def mcp_http_health_url(self) -> str:
        """Return the local MCP process health-check URL."""
        host = f"[{self.mcp_http_host}]" if ":" in self.mcp_http_host else self.mcp_http_host
        return f"http://{host}:{self.mcp_http_port}{self.mcp_http_health_path}"


def load_settings() -> Settings:
    auth_enabled = _read_bool("AUTH_ENABLED", False)
    api_key = os.getenv("MCP_API_KEY", "").strip()
    if auth_enabled and len(api_key) < 16:
        raise ConfigurationError(
            "MCP_API_KEY must contain at least 16 characters when AUTH_ENABLED=true."
        )

    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:3000").strip().rstrip("/")
    parsed_api_url = urlsplit(api_base_url)
    if parsed_api_url.scheme not in {"http", "https"} or not parsed_api_url.netloc:
        raise ConfigurationError("API_BASE_URL must be a valid http:// or https:// URL.")

    mcp_transport = _read_transport()
    mcp_http_host = os.getenv("MCP_HTTP_HOST", "127.0.0.1").strip()
    if not mcp_http_host:
        raise ConfigurationError("MCP_HTTP_HOST cannot be empty.")
    mcp_http_path = _read_http_path("MCP_HTTP_PATH", "/mcp")
    mcp_http_health_path = _read_http_path("MCP_HTTP_HEALTH_PATH", "/health")
    if mcp_http_path == mcp_http_health_path:
        raise ConfigurationError("MCP_HTTP_PATH and MCP_HTTP_HEALTH_PATH must be different.")

    settings = Settings(
        api_base_url=api_base_url,
        # Usage/activity scans can exceed 10s; keep default high enough for find_usage.
        api_timeout_seconds=_read_positive_float("API_TIMEOUT_SECONDS", 120.0),
        api_max_retries=_read_non_negative_int("API_MAX_RETRIES", 2),
        auth_enabled=auth_enabled,
        api_key=api_key,
        server_name=os.getenv("MCP_SERVER_NAME", "Adobe Tags MCP").strip(),
        log_level=_read_log_level(),
        mcp_transport=mcp_transport,
        mcp_http_host=mcp_http_host,
        mcp_http_port=_read_port("MCP_HTTP_PORT", 8000),
        mcp_http_path=mcp_http_path,
        mcp_http_health_path=mcp_http_health_path,
        mcp_http_stateless=_read_bool("MCP_HTTP_STATELESS", True),
        mcp_http_json_response=_read_bool("MCP_HTTP_JSON_RESPONSE", True),
        mcp_http_max_request_body_bytes=_read_positive_int(
            "MCP_HTTP_MAX_REQUEST_BODY_BYTES", 4 * 1024 * 1024
        ),
    )
    validate_runtime_settings(settings)
    return settings
