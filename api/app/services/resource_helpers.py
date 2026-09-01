from __future__ import annotations

from typing import Any

from app.adobe.jsonapi import max_revision_number, parse_latest_revision_number, resource_meta
from app.adobe.list_pages import fetch_all_list_pages
from app.adobe.reactor_client import ReadOnlyReactorClient, ReactorApiError


async def fetch_resource_with_meta(
    reactor: ReadOnlyReactorClient,
    path: str,
    *,
    not_found_message: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = await reactor.get(path)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ReactorApiError("NOT_FOUND", not_found_message, 404)
    return data, resource_meta(data, payload)


async def resolve_resource_version(
    reactor: ReadOnlyReactorClient,
    revisions_path: str,
    *,
    resource_meta_dict: dict[str, Any],
) -> int:
    try:
        revisions = await fetch_all_list_pages(
            reactor,
            revisions_path,
            page_size=50,
            max_pages=5,
        )
        from_revisions = max_revision_number(revisions)
        if from_revisions is not None:
            return from_revisions
    except ReactorApiError:
        pass

    from_meta = parse_latest_revision_number(resource_meta_dict)
    if from_meta is not None:
        return from_meta
    return 0
