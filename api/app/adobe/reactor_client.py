from __future__ import annotations

from typing import Any

import httpx

from app.auth.base import AdobeAuthProvider


class ReadOnlyViolationError(RuntimeError):
    """Raised when a non-read Reactor operation is attempted."""


class ReactorApiError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ReadOnlyReactorClient:
    _ALLOWED_POST_PATHS = {"/search"}

    def __init__(self, auth: AdobeAuthProvider, base_url: str):
        self._auth = auth
        self._base_url = base_url.rstrip("/")

    def _validate_method(self, method: str, path: str) -> None:
        normalized = path.split("?", 1)[0]
        if method.upper() == "GET":
            return
        if method.upper() == "POST" and normalized in self._ALLOWED_POST_PATHS:
            return
        raise ReadOnlyViolationError(
            f"Blocked non-read Reactor request: {method.upper()} {normalized}"
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._validate_method(method, path)
        headers_data = await self._auth.get_headers()
        headers = {
            "Authorization": headers_data.authorization,
            "x-api-key": headers_data.api_key,
            "x-gw-ims-org-id": headers_data.org_id,
            "Accept": "application/vnd.api+json;revision=1",
            "Content-Type": "application/vnd.api+json",
        }
        async with httpx.AsyncClient(base_url=self._base_url, timeout=60.0) as client:
            response = await client.request(method, path, params=params, json=json, headers=headers)

        if response.status_code == 401:
            raise ReactorApiError("ADOBE_UNAUTHORIZED", "Adobe access token is invalid or expired.", 401)
        if response.status_code == 403:
            raise ReactorApiError(
                "ADOBE_FORBIDDEN",
                "Your Adobe account lacks permission for this Tags resource or action.",
                403,
            )
        if response.is_error:
            raise ReactorApiError(
                "REACTOR_REQUEST_FAILED",
                f"Adobe Reactor API request failed with status {response.status_code}.",
                response.status_code,
            )
        return response.json()

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.request("GET", path, params=params)

    async def search(self, query: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", "/search", json={"data": query})
