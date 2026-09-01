from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import StrictModel


class HealthResult(StrictModel):
    status: Literal["healthy"]
    service: str


class SystemStatusResult(StrictModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str
    uptime_seconds: int = Field(alias="uptimeSeconds")
    current_time: str = Field(alias="currentTime")
    authentication_enabled: bool = Field(alias="authenticationEnabled")
