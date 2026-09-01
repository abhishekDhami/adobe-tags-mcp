from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request

from app.adobe.reactor_client import ReactorApiError
from app.auth.server_to_server import AdobeAuthError as ServerAdobeAuthError
from app.auth.user_oauth import AdobeAuthError as UserAdobeAuthError
from app.common.responses import error_response, success_response
from app.services.usage import UsageServiceError

router = APIRouter(prefix="/api/v1/tags", tags=["analysis"])

VersionScope = Literal["latest", "live"]


def _handle_errors(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    if isinstance(exc, UsageServiceError):
        return error_response(
            status_code=400,
            code=exc.code,
            message=exc.message,
            request_id=request_id,
        )
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


@router.get("/rules/{rule_id}/dependencies")
async def get_rule_dependencies(
    request: Request,
    rule_id: str,
    version_scope: VersionScope = Query("latest", alias="versionScope"),
):
    """Scan rule components for data element and extension dependencies.

    versionScope=latest (default): scan the current head/working rule.
    versionScope=live: scan the production revision; empty graph if never published.
    """
    try:
        data = await request.app.state.analysis_service.get_rule_dependencies(
            rule_id,
            version_scope=version_scope,
        )
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)


@router.get("/properties/{property_id}/usage")
async def find_property_usage(
    request: Request,
    property_id: str,
    query: str = Query(..., min_length=1, description="Data element name/id, or free-text when mode=freeText."),
    version_scope: VersionScope = Query(
        "latest",
        alias="versionScope",
        description=(
            "latest (default): working/saved revisions (revision_number=0 filter). "
            "live: published/production revisions. AI should state which scope was used."
        ),
    ),
    mode: Literal["dataElement", "freeText"] = Query(
        "freeText",
        description=(
            "freeText (default): settings substring search (unknown keywords). "
            "dataElement: resolve a DE and find token/getVar references only."
        ),
    ),
    detail: Literal["hits", "summary", "components"] = Query(
        "hits",
        description=(
            "hits (default): fast UI-like high-level list only. "
            "summary/components: enriched consumers (slower)."
        ),
    ),
    library_id: str | None = Query(
        None,
        alias="libraryId",
        description="Optional library id — only for detail=summary|components enrichment filter.",
    ),
):
    """Find where a data element or free-text string is used (Reactor /search + verify).

    Default is a fast property-scoped hit list (detail=hits, versionScope=latest, mode=freeText).
    Pass mode=dataElement when the user is asking specifically about a known data element;
    ambiguous DE names then return status=needsDisambiguation (no scan).
    If mode=dataElement and no DE matches, automatically falls back to freeText.
    """
    try:
        data = await request.app.state.usage_service.find_usage(
            property_id,
            query=query,
            version_scope=version_scope,
            mode=mode,
            detail=detail,
            library_id=library_id,
        )
    except Exception as exc:
        return _handle_errors(request, exc)
    request_id = getattr(request.state, "request_id", None)
    return success_response(data, request_id=request_id)
