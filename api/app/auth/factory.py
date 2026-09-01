from __future__ import annotations

from app.auth.base import AdobeAuthProvider
from app.auth.server_to_server import ServerToServerAuthProvider
from app.auth.session_store import SessionStore
from app.auth.user_oauth import UserOAuthAuthProvider
from app.config import Settings


def create_auth_provider(settings: Settings, store: SessionStore | None = None) -> AdobeAuthProvider:
    session_store = store or SessionStore(settings.data_dir / "session.json", settings.vault_key)
    if settings.adobe_auth_mode == "user_oauth":
        return UserOAuthAuthProvider(settings, session_store)
    return ServerToServerAuthProvider(settings)
