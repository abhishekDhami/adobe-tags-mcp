from __future__ import annotations

from fastapi import APIRouter, Request

from app.common.responses import success_response
from app.services.system import get_system_status

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/status")
async def system_status(request: Request):
    settings = request.app.state.settings
    status = get_system_status(settings)
    request_id = getattr(request.state, "request_id", None)
    return success_response(
        {
            "status": status.status,
            "service": status.service,
            "version": status.version,
            "environment": status.environment,
            "uptimeSeconds": status.uptime_seconds,
            "currentTime": status.current_time,
            "authenticationEnabled": status.authentication_enabled,
        },
        request_id=request_id,
    )
