from __future__ import annotations

from fastapi import APIRouter, Request

from app.common.responses import success_response

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request):
    settings = request.app.state.settings
    request_id = getattr(request.state, "request_id", None)
    return success_response(
        {"status": "healthy", "service": settings.service_name},
        request_id=request_id,
    )


@router.get("/ready")
async def ready(request: Request):
    request_id = getattr(request.state, "request_id", None)
    return success_response({"status": "ready"}, request_id=request_id)
