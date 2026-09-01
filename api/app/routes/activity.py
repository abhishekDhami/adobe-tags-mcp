from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request

from app.adobe.reactor_client import ReactorApiError
from app.auth.server_to_server import AdobeAuthError as ServerAdobeAuthError
from app.auth.user_oauth import AdobeAuthError as UserAdobeAuthError
from app.common.responses import error_response, success_response
from app.services.activity import ActivityServiceError

router = APIRouter(prefix="/api/v1/tags", tags=["activity"])


def _handle_errors(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    if isinstance(exc, ActivityServiceError):
        return error_response(
            status_code=400,
            code=exc.code,
            message=exc.message,
            request_id=request_id,
        )
    if isinstance(exc, (ServerAdobeAuthError, UserAdobeAuthError)):
        status = 401 if exc.code in {"NOT_CONNECTED", "ADOBE_UNAUTHORIZED"} else 400
        return error_response(
            status_code=status, code=exc.code, message=exc.message, request_id=request_id
        )
    if isinstance(exc, ReactorApiError):
        return error_response(
            status_code=exc.status_code or 502,
            code=exc.code,
            message=exc.message,
            request_id=request_id,
        )
    raise exc


@router.get("/properties/{property_id}/activity")
async def get_property_activity(
    request: Request,
    property_id: str,
    from_value: str | None = Query(
        None,
        alias="from",
        description="Window start (YYYY-MM-DD or ISO-8601). Inclusive.",
    ),
    to_value: str | None = Query(
        None,
        alias="to",
        description="Window end (YYYY-MM-DD or ISO-8601). Date-only = end of that UTC day.",
    ),
    focus: Literal["deployments", "edits", "all"] = Query(
        "all",
        description="deployments = published libraries; edits = audit events; all = both.",
    ),
    prior_deploy_limit: int = Query(
        3,
        alias="priorDeployLimit",
        ge=1,
        le=10,
        description=(
            "When no deployments fall in the window, return this many published "
            "libraries strictly before the window start (not the latest overall)."
        ),
    ),
):
    """Property activity for a time window: deployments + resource edit audit events.

    If no deployments are in the window, priorToWindow lists the last N publishes
    before the window start (e.g. ask March 2025 → last 3 deploys before March 2025).
    """
    try:
        data = await request.app.state.activity_service.get_property_activity(
            property_id,
            from_value=from_value,
            to_value=to_value,
            focus=focus,
            prior_deploy_limit=prior_deploy_limit,
        )
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)
