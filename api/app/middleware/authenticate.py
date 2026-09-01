from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.common.responses import error_response
from app.config import Settings

_PUBLIC_PREFIXES = ("/health", "/ready", "/auth/", "/docs", "/openapi.json")


class AuthenticateMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self._settings = settings

    def _is_public(self, path: str) -> bool:
        return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._settings.auth_enabled or self._is_public(request.url.path):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        expected = f"Bearer {self._settings.mcp_api_key}"
        if auth_header != expected:
            request_id = getattr(request.state, "request_id", None)
            return error_response(
                status_code=401,
                code="UNAUTHORIZED",
                message="Valid MCP service authentication is required.",
                request_id=request_id,
            )

        return await call_next(request)
