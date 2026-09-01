from __future__ import annotations

import time
from dataclasses import dataclass

from app.config import Settings


@dataclass(slots=True)
class SystemStatus:
    status: str
    service: str
    version: str
    environment: str
    uptime_seconds: int
    current_time: str
    authentication_enabled: bool


_started_at = time.monotonic()


def get_system_status(settings: Settings) -> SystemStatus:
    from app.common.responses import utc_now_iso

    return SystemStatus(
        status="ok",
        service=settings.service_name,
        version=settings.api_version,
        environment=settings.environment,
        uptime_seconds=int(time.monotonic() - _started_at),
        current_time=utc_now_iso(),
        authentication_enabled=settings.auth_enabled,
    )
