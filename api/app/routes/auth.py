from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from app.adobe.reactor_client import ReactorApiError
from app.auth.server_to_server import AdobeAuthError as ServerAdobeAuthError
from app.auth.user_oauth import AdobeAuthError as UserAdobeAuthError
from app.common.responses import error_response, success_response

router = APIRouter(tags=["auth"])


def _auth_error_response(request: Request, exc: ServerAdobeAuthError | UserAdobeAuthError):
    request_id = getattr(request.state, "request_id", None)
    status = 401 if exc.code in {"NOT_CONNECTED", "ADOBE_UNAUTHORIZED", "OAUTH_TOKEN_FAILED"} else 400
    return error_response(
        status_code=status,
        code=exc.code,
        message=exc.message,
        request_id=request_id,
    )


@router.get("/api/v1/auth/status")
async def auth_status(request: Request):
    provider = request.app.state.auth_provider
    status = await provider.get_connection_status()
    request_id = getattr(request.state, "request_id", None)
    return success_response(
        {
            "connected": status.connected,
            "mode": status.mode,
            "orgId": status.org_id,
            "userEmail": status.user_email,
            "message": status.message,
        },
        request_id=request_id,
    )


@router.post("/api/v1/auth/disconnect")
async def auth_disconnect(request: Request):
    await request.app.state.auth_provider.clear_session()
    request.app.state.session_manager.clear_workspace()
    request_id = getattr(request.state, "request_id", None)
    return success_response({"disconnected": True}, request_id=request_id)


@router.get("/auth/adobe/start")
async def adobe_oauth_start(request: Request):
    settings = request.app.state.settings
    if settings.adobe_auth_mode != "user_oauth":
        request_id = getattr(request.state, "request_id", None)
        return error_response(
            status_code=400,
            code="INVALID_AUTH_MODE",
            message="Adobe browser login is only available when ADOBE_AUTH_MODE=user_oauth.",
            request_id=request_id,
        )
    provider = request.app.state.auth_provider
    url, _state = provider.build_authorize_url()
    return RedirectResponse(url)


@router.get("/auth/adobe/callback")
async def adobe_oauth_callback(request: Request, code: str = "", state: str = ""):
    provider = request.app.state.auth_provider
    try:
        await provider.complete_callback(code=code, state=state)
    except UserAdobeAuthError as exc:
        request_id = getattr(request.state, "request_id", None)
        return error_response(
            status_code=400,
            code=exc.code,
            message=exc.message,
            request_id=request_id,
        )
    return RedirectResponse("/auth/adobe/success")


@router.get("/auth/adobe/success")
async def adobe_oauth_success():
    return {"status": "connected", "message": "Adobe sign-in complete. You can return to ChatGPT."}
