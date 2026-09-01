from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request

from app.adobe.reactor_client import ReactorApiError
from app.auth.server_to_server import AdobeAuthError as ServerAdobeAuthError
from app.auth.user_oauth import AdobeAuthError as UserAdobeAuthError
from app.common.responses import error_response, success_response
from app.presenters.options import ViewDepth, ViewOptions

RevisionViewParam = Literal["important", "full"]

router = APIRouter(prefix="/api/v1/tags", tags=["tags"])


def _handle_errors(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    if isinstance(exc, (ServerAdobeAuthError, UserAdobeAuthError)):
        status = 401 if exc.code in {"NOT_CONNECTED", "ADOBE_UNAUTHORIZED"} else 400
        return error_response(status_code=status, code=exc.code, message=exc.message, request_id=request_id)
    if isinstance(exc, ReactorApiError):
        return error_response(
            status_code=exc.status_code or 502,
            code=exc.code,
            message=exc.message,
            request_id=request_id,
        )
    raise exc


def _view_options(
    *,
    depth: ViewDepth,
    include_code: bool,
    include_raw_settings: bool,
) -> ViewOptions:
    return ViewOptions(
        depth=depth,
        include_code=include_code,
        include_raw_settings=include_raw_settings,
    )


@router.get("/properties")
async def list_properties(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(0, ge=0, alias="pageSize"),
):
    try:
        data = await request.app.state.tags_service.list_properties(page=page, page_size=page_size)
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/properties/{property_id}/rules")
async def list_rules(
    request: Request,
    property_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(0, ge=0, alias="pageSize"),
    search: str | None = Query(None),
):
    try:
        data = await request.app.state.tags_service.list_rules(
            property_id, page=page, page_size=page_size, search=search
        )
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/rules/{rule_id}")
async def get_rule(
    request: Request,
    rule_id: str,
    depth: ViewDepth = Query("context"),
    include_code: bool = Query(False, alias="includeCode"),
    include_raw_settings: bool = Query(False, alias="includeRawSettings"),
):
    try:
        data = await request.app.state.tags_service.get_rule(
            rule_id,
            options=_view_options(
                depth=depth,
                include_code=include_code,
                include_raw_settings=include_raw_settings,
            ),
        )
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/rules/{rule_id}/rule-components")
async def list_rule_components(request: Request, rule_id: str):
    try:
        data = await request.app.state.tags_service.list_rule_components(rule_id)
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/rules/{rule_id}/versions")
async def list_rule_versions(
    request: Request,
    rule_id: str,
    view: RevisionViewParam = Query(
        "important",
        description="important (default): only roles inDevelopmentLibrary / headNotInDevLibrary / publishedOrLive. full: all revisions.",
    ),
):
    try:
        data = await request.app.state.revision_service.list_rule_revisions(rule_id, view=view)
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/properties/{property_id}/data-elements")
async def list_data_elements(
    request: Request,
    property_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(0, ge=0, alias="pageSize"),
    search: str | None = Query(None),
):
    try:
        data = await request.app.state.tags_service.list_data_elements(
            property_id, page=page, page_size=page_size, search=search
        )
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/data-elements/{data_element_id}")
async def get_data_element(
    request: Request,
    data_element_id: str,
    depth: ViewDepth = Query("detail"),
    include_code: bool = Query(False, alias="includeCode"),
    include_raw_settings: bool = Query(False, alias="includeRawSettings"),
):
    try:
        data = await request.app.state.tags_service.get_data_element(
            data_element_id,
            options=_view_options(
                depth=depth,
                include_code=include_code,
                include_raw_settings=include_raw_settings,
            ),
        )
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/data-elements/{data_element_id}/versions")
async def list_data_element_versions(
    request: Request,
    data_element_id: str,
    view: RevisionViewParam = Query(
        "important",
        description="important (default): only roles inDevelopmentLibrary / headNotInDevLibrary / publishedOrLive. full: all revisions.",
    ),
):
    try:
        data = await request.app.state.revision_service.list_data_element_revisions(
            data_element_id, view=view
        )
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/properties/{property_id}/extensions")
async def list_extensions(
    request: Request,
    property_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(0, ge=0, alias="pageSize"),
):
    try:
        data = await request.app.state.tags_service.list_extensions(
            property_id, page=page, page_size=page_size
        )
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/extensions/{extension_id}")
async def get_extension(
    request: Request,
    extension_id: str,
    depth: ViewDepth = Query("detail"),
    include_raw_settings: bool = Query(False, alias="includeRawSettings"),
):
    try:
        data = await request.app.state.tags_service.get_extension(
            extension_id,
            options=_view_options(
                depth=depth,
                include_code=False,
                include_raw_settings=include_raw_settings,
            ),
        )
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/extensions/{extension_id}/versions")
async def list_extension_versions(
    request: Request,
    extension_id: str,
    view: RevisionViewParam = Query(
        "important",
        description="important (default): only roles inDevelopmentLibrary / headNotInDevLibrary / publishedOrLive. full: all revisions.",
    ),
):
    try:
        data = await request.app.state.revision_service.list_extension_revisions(
            extension_id, view=view
        )
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/search")
async def search_resources(
    request: Request,
    query: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(0, ge=0, alias="pageSize"),
    resource_types: list[str] | None = Query(None, alias="resourceTypes"),
):
    try:
        data = await request.app.state.tags_service.search_resources(
            query=query,
            resource_types=resource_types,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)
