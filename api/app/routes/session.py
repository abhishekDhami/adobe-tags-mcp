from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from app.common.responses import success_response

router = APIRouter(prefix="/api/v1/session", tags=["session"])


class SessionUpdateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    active_property_id: str | None = Field(default=None, alias="activePropertyId")
    active_property_name: str | None = Field(default=None, alias="activePropertyName")
    active_library_id: str | None = Field(default=None, alias="activeLibraryId")
    active_library_name: str | None = Field(default=None, alias="activeLibraryName")


@router.get("")
async def get_session(request: Request):
    data = request.app.state.session_manager.present_session()
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.patch("")
async def update_session(request: Request, body: SessionUpdateBody):
    data = request.app.state.session_manager.update_workspace(
        active_property_id=body.active_property_id,
        active_property_name=body.active_property_name,
        active_library_id=body.active_library_id,
        active_library_name=body.active_library_name,
    )
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.post("/clear")
async def clear_session(request: Request):
    request.app.state.session_manager.clear_workspace()
    request_id = getattr(request.state, "request_id", None)
    return success_response({"cleared": True}, request_id=request_id)
