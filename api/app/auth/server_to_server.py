from __future__ import annotations

import time
from typing import Any

import httpx

from app.auth.base import AuthHeaders, ConnectionStatus
from app.config import Settings


class AdobeAuthError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ServerToServerAuthProvider:
    mode = "server_to_server"

    def __init__(self, settings: Settings):
        self._settings = settings
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    def _validate_config(self) -> None:
        missing = [
            name
            for name, value in (
                ("ADOBE_CLIENT_ID", self._settings.adobe_client_id),
                ("ADOBE_CLIENT_SECRET", self._settings.adobe_client_secret),
                ("ADOBE_ORG_ID", self._settings.adobe_org_id),
            )
            if not value
        ]
        if missing:
            raise AdobeAuthError(
                "ADOBE_NOT_CONFIGURED",
                f"Missing required settings: {', '.join(missing)}",
            )

    async def _fetch_token(self) -> str:
        self._validate_config()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self._settings.adobe_ims_token_url,
                data={
                    "client_id": self._settings.adobe_client_id,
                    "client_secret": self._settings.adobe_client_secret,
                    "grant_type": "client_credentials",
                    "scope": self._settings.adobe_scopes,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if response.is_error:
            raise AdobeAuthError(
                "ADOBE_TOKEN_FAILED",
                "Failed to obtain Adobe access token. Check credentials and scopes.",
            )
        payload: dict[str, Any] = response.json()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise AdobeAuthError("ADOBE_TOKEN_FAILED", "Adobe token response missing access_token.")
        expires_in = int(payload.get("expires_in", 86400))
        self._access_token = token
        self._expires_at = time.time() + max(expires_in - 300, 60)
        return token

    async def get_access_token(self) -> str:
        if self._access_token and time.time() < self._expires_at:
            return self._access_token
        return await self._fetch_token()

    async def get_headers(self) -> AuthHeaders:
        token = await self.get_access_token()
        return AuthHeaders(
            authorization=f"Bearer {token}",
            api_key=self._settings.adobe_client_id,
            org_id=self._settings.adobe_org_id,
        )

    async def get_connection_status(self) -> ConnectionStatus:
        try:
            self._validate_config()
            await self.get_access_token()
            return ConnectionStatus(
                connected=True,
                mode="server_to_server",
                org_id=self._settings.adobe_org_id,
                user_email=None,
                message="Connected via Adobe Server-to-Server credentials.",
            )
        except AdobeAuthError as exc:
            return ConnectionStatus(
                connected=False,
                mode="server_to_server",
                org_id=self._settings.adobe_org_id or None,
                user_email=None,
                message=exc.message,
            )

    async def clear_session(self) -> None:
        self._access_token = None
        self._expires_at = 0.0
