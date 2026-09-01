from __future__ import annotations

from typing import Any

from app.auth.session_store import SessionStore

WORKSPACE_KEY = "workspace"


class SessionManager:
    """Persist practitioner workspace hints (active property/library) in the session vault."""

    def __init__(self, store: SessionStore) -> None:
        self._store = store

    def get_workspace(self) -> dict[str, Any]:
        session = self._store.load()
        workspace = session.get(WORKSPACE_KEY)
        if isinstance(workspace, dict):
            return dict(workspace)
        return {}

    def update_workspace(
        self,
        *,
        active_property_id: str | None = None,
        active_property_name: str | None = None,
        active_library_id: str | None = None,
        active_library_name: str | None = None,
    ) -> dict[str, Any]:
        session = self._store.load()
        workspace = session.get(WORKSPACE_KEY)
        if not isinstance(workspace, dict):
            workspace = {}

        updates = {
            "activePropertyId": active_property_id,
            "activePropertyName": active_property_name,
            "activeLibraryId": active_library_id,
            "activeLibraryName": active_library_name,
        }
        for key, value in updates.items():
            if value is not None:
                workspace[key] = value

        session[WORKSPACE_KEY] = workspace
        self._store.save(session)
        return dict(workspace)

    def clear_workspace(self) -> None:
        session = self._store.load()
        if WORKSPACE_KEY in session:
            session.pop(WORKSPACE_KEY, None)
            if session:
                self._store.save(session)
            else:
                self._store.clear()

    def present_session(self) -> dict[str, Any]:
        workspace = self.get_workspace()
        return {
            "activePropertyId": workspace.get("activePropertyId"),
            "activePropertyName": workspace.get("activePropertyName"),
            "activeLibraryId": workspace.get("activeLibraryId"),
            "activeLibraryName": workspace.get("activeLibraryName"),
        }
