from __future__ import annotations

from typing import Any

from app.adobe.jsonapi import as_list, reactor_page_number
from app.adobe.reactor_client import ReadOnlyReactorClient


async def fetch_all_list_pages(
    reactor: ReadOnlyReactorClient,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    page_size: int = 50,
    max_pages: int = 20,
) -> list[dict[str, Any]]:
    """Follow Adobe Reactor pagination until next_page is null (1-based page[number]).

    Adobe documents next_page in meta.pagination; see Reactor pagination guide.
    """
    items: list[dict[str, Any]] = []
    page = 1
    base_params = dict(params or {})

    for _ in range(max_pages):
        request_params = {
            **base_params,
            "page[size]": page_size,
            "page[number]": reactor_page_number(page),
        }
        payload = await reactor.get(path, params=request_params)
        items.extend(as_list(payload))
        pagination = (payload.get("meta") or {}).get("pagination") or {}
        next_page = pagination.get("next_page")
        if next_page is None:
            break
        next_page_int = int(next_page)
        if next_page_int <= page:
            break
        page = next_page_int

    return items
