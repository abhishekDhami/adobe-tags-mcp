from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ApiErrorPayload(StrictModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ApiMeta(StrictModel):
    request_id: str = Field(alias="requestId")
    timestamp: str
    pagination: dict[str, int] | None = None


class ApiSuccessEnvelope(StrictModel):
    success: Literal[True]
    data: Any
    meta: ApiMeta


class ApiErrorEnvelope(StrictModel):
    success: Literal[False]
    error: ApiErrorPayload
    meta: ApiMeta
