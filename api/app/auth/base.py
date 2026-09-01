from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

AdobeAuthMode = Literal["user_oauth", "server_to_server"]


@dataclass(frozen=True, slots=True)
class AuthHeaders:
    authorization: str
    api_key: str
    org_id: str


@dataclass(frozen=True, slots=True)
class ConnectionStatus:
    connected: bool
    mode: AdobeAuthMode | None
    org_id: str | None
    user_email: str | None
    message: str


class AdobeAuthProvider(Protocol):
    mode: AdobeAuthMode

    async def get_headers(self) -> AuthHeaders: ...

    async def get_connection_status(self) -> ConnectionStatus: ...

    async def clear_session(self) -> None: ...
