from __future__ import annotations

from typing import Any

import asyncio

from app.adobe.list_pages import fetch_all_list_pages


class PaginatedReactor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((path, params))
        page = (params or {}).get("page[number]", 1)
        if page == 1:
            return {
                "data": [{"id": "LB1", "type": "libraries", "attributes": {"name": "A"}}],
                "meta": {"pagination": {"next_page": 2, "total_count": 2}},
            }
        return {
            "data": [{"id": "LB2", "type": "libraries", "attributes": {"name": "B"}}],
            "meta": {"pagination": {"next_page": None, "total_count": 2}},
        }


def test_fetch_all_list_pages_stops_on_stuck_next_page() -> None:
    class StuckReactor:
        def __init__(self) -> None:
            self.calls = 0

        async def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
            self.calls += 1
            return {
                "data": [{"id": f"LB{self.calls}"}],
                "meta": {"pagination": {"next_page": 1}},
            }

    reactor = StuckReactor()
    items = asyncio.run(fetch_all_list_pages(reactor, "/properties/PR1/libraries"))
    assert len(items) == 1
    assert reactor.calls == 1


def test_fetch_all_list_pages_follows_adobe_next_page() -> None:
    reactor = PaginatedReactor()
    items = asyncio.run(fetch_all_list_pages(reactor, "/properties/PR1/libraries"))
    assert len(items) == 2
    assert items[0]["id"] == "LB1"
    assert items[1]["id"] == "LB2"
    assert reactor.calls[0][1]["page[number]"] == 1
    assert reactor.calls[1][1]["page[number]"] == 2
