from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class SessionStore:
    """Persist auth session data under data/ with optional Fernet encryption."""

    def __init__(self, path: Path, vault_key: str = "") -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(vault_key.encode()) if vault_key else None

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        raw = self._path.read_bytes()
        if self._fernet:
            try:
                raw = self._fernet.decrypt(raw)
            except InvalidToken:
                return {}
        return json.loads(raw.decode("utf-8"))

    def save(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if self._fernet:
            encoded = self._fernet.encrypt(encoded)
        self._path.write_bytes(encoded)

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()
