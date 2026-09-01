from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from app.auth.base import AuthHeaders, ConnectionStatus
from app.auth.session_store import SessionStore
from app.config import Settings


class AdobeAuthError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class UserOAuthAuthProvider:
    mode = "user_oauth"

    def __init__(self, settings: Settings, store: SessionStore):
        self._settings = settings
        self._store = store

    def _validate_oauth_config(self) -> None:
        missing = [
            name
            for name, value in (
                ("ADOBE_CLIENT_ID", self._settings.adobe_client_id),
                ("ADOBE_CLIENT_SECRET", self._settings.adobe_client_secret),
                ("ADOBE_ORG_ID", self._settings.adobe_org_id),
                ("ADOBE_OAUTH_REDIRECT_URI", self._settings.adobe_oauth_redirect_uri),
            )
            if not value
        ]
        if missing:
            raise AdobeAuthError(
                "ADOBE_NOT_CONFIGURED",
                f"Missing required OAuth settings: {', '.join(missing)}",
            )

    def _session(self) -> dict[str, Any]:
        return self._store.load()

    def build_authorize_url(self) -> tuple[str, str]:
        self._validate_oauth_config()
        state = secrets.token_urlsafe(24)
        session = self._session()
        session["oauth_state"] = state
        self._store.save(session)
        params = urlencode(
            {
                "client_id": self._settings.adobe_client_id,
                "redirect_uri": self._settings.adobe_oauth_redirect_uri,
                "scope": self._settings.adobe_scopes,
                "state": state,
                "response_type": "code",
            }
        )
        return f"{self._settings.adobe_ims_authorize_url}?{params}", state

    async def complete_callback(self, code: str, state: str) -> None:
        session = self._session()
        expected_state = session.get("oauth_state")
        if not expected_state or expected_state != state:
            raise AdobeAuthError("OAUTH_STATE_MISMATCH", "OAuth state validation failed.")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self._settings.adobe_ims_token_url,
                data={
                    "client_id": self._settings.adobe_client_id,
                    "client_secret": self._settings.adobe_client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._settings.adobe_oauth_redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if response.is_error:
            raise AdobeAuthError("OAUTH_TOKEN_FAILED", "Failed to exchange Adobe authorization code.")

        payload: dict[str, Any] = response.json()
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise AdobeAuthError("OAUTH_TOKEN_FAILED", "Adobe token response missing access_token.")

        expires_in = int(payload.get("expires_in", 86400))
        session.update(
            {
                "access_token": access_token,
                "refresh_token": payload.get("refresh_token"),
                "expires_at": time.time() + max(expires_in - 300, 60),
                "user_email": payload.get("email"),
            }
        )
        session.pop("oauth_state", None)
        self._store.save(session)

    async def _ensure_access_token(self) -> str:
        session = self._session()
        token = session.get("access_token")
        expires_at = float(session.get("expires_at", 0))
        if isinstance(token, str) and token and time.time() < expires_at:
            return token

        refresh_token = session.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise AdobeAuthError(
                "NOT_CONNECTED",
                "Adobe user session is not connected. Open /auth/adobe/start to sign in.",
            )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self._settings.adobe_ims_token_url,
                data={
                    "client_id": self._settings.adobe_client_id,
                    "client_secret": self._settings.adobe_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if response.is_error:
            raise AdobeAuthError("OAUTH_REFRESH_FAILED", "Adobe refresh token is invalid or expired.")

        payload: dict[str, Any] = response.json()
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise AdobeAuthError("OAUTH_REFRESH_FAILED", "Adobe refresh response missing access_token.")

        expires_in = int(payload.get("expires_in", 86400))
        session["access_token"] = access_token
        session["expires_at"] = time.time() + max(expires_in - 300, 60)
        if payload.get("refresh_token"):
            session["refresh_token"] = payload["refresh_token"]
        self._store.save(session)
        return access_token

    async def get_headers(self) -> AuthHeaders:
        token = await self._ensure_access_token()
        return AuthHeaders(
            authorization=f"Bearer {token}",
            api_key=self._settings.adobe_client_id,
            org_id=self._settings.adobe_org_id,
        )

    async def get_connection_status(self) -> ConnectionStatus:
        session = self._session()
        has_token = bool(session.get("access_token") or session.get("refresh_token"))
        if not has_token:
            return ConnectionStatus(
                connected=False,
                mode="user_oauth",
                org_id=self._settings.adobe_org_id or None,
                user_email=None,
                message="Not connected. Open /auth/adobe/start to sign in with Adobe.",
            )
        try:
            await self._ensure_access_token()
            return ConnectionStatus(
                connected=True,
                mode="user_oauth",
                org_id=self._settings.adobe_org_id,
                user_email=session.get("user_email"),
                message="Connected via Adobe user OAuth.",
            )
        except AdobeAuthError as exc:
            return ConnectionStatus(
                connected=False,
                mode="user_oauth",
                org_id=self._settings.adobe_org_id or None,
                user_email=session.get("user_email"),
                message=exc.message,
            )

    async def clear_session(self) -> None:
        self._store.clear()
