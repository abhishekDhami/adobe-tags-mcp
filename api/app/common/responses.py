from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi.responses import JSONResponse


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_meta(request_id: str | None = None, pagination: dict[str, int] | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "requestId": request_id or str(uuid4()),
        "timestamp": utc_now_iso(),
    }
    if pagination is not None:
        meta["pagination"] = pagination
    return meta


def success_response(data: Any, request_id: str | None = None) -> JSONResponse:
    return JSONResponse(
        {
            "success": True,
            "data": data,
            "meta": build_meta(request_id=request_id),
        }
    )


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str | None = None,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "details": details,
            },
            "meta": build_meta(request_id=request_id),
        },
    )
