from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request

from app.adobe.reactor_client import ReactorApiError
from app.auth.server_to_server import AdobeAuthError as ServerAdobeAuthError
from app.auth.user_oauth import AdobeAuthError as UserAdobeAuthError
from app.common.responses import error_response, success_response
from app.services.libraries import LibraryResourceFilter

router = APIRouter(prefix="/api/v1/tags", tags=["libraries"])


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


@router.get("/properties/{property_id}/environments")
async def list_environments(request: Request, property_id: str):
    try:
        data = await request.app.state.libraries_service.list_environments(property_id)
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/properties/{property_id}/development-libraries")
async def get_development_library(request: Request, property_id: str):
    """Resolve the active development library for pre-publish review."""
    try:
        data = await request.app.state.libraries_service.get_development_library(property_id)
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/properties/{property_id}/published-libraries")
async def list_published_libraries(
    request: Request,
    property_id: str,
    page: int = Query(1, ge=1, description="Page number (1-based). Use 2 for the next page."),
    page_size: int = Query(0, ge=0, alias="pageSize", description="Items per page (default 25, max 50)."),
    state: str = Query(
        "published",
        description="Library state filter. Defaults to published (historical publish snapshots).",
    ),
    environment_id: str | None = Query(None, alias="environmentId"),
    sort: str = Query(
        "-published_at",
        description="Adobe sort order. Default -published_at = newest publish first.",
    ),
):
    """List libraries that have been through the publish workflow (default: published)."""
    try:
        data = await request.app.state.libraries_service.list_published_libraries(
            property_id,
            page=page,
            page_size=page_size,
            state=state,
            environment_id=environment_id,
            sort=sort,
        )
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/libraries/{library_id}/review-development-library")
async def review_development_library(
    request: Request,
    library_id: str,
    depth: Literal["summary", "full"] = Query("summary"),
):
    """Pre-publish review of resources in a development library.

    Compares each library member to its production live revision:
    new (pending only), modified (publishedLive + pending), disabled (live enabled → pending disabled).
    """
    try:
        data = await request.app.state.libraries_service.review_development_library(
            library_id,
            depth=depth,
        )
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/libraries/{library_id}")
async def get_library(request: Request, library_id: str):
    try:
        data = await request.app.state.libraries_service.get_library(library_id)
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/libraries/{library_id}/resources")
async def list_library_resources(
    request: Request,
    library_id: str,
    resource_type: LibraryResourceFilter = Query("all", alias="resourceType"),
    page: int = Query(1, ge=1),
    page_size: int = Query(0, ge=0, alias="pageSize"),
):
    try:
        data = await request.app.state.libraries_service.list_library_resources(
            library_id,
            resource_type=resource_type,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)
