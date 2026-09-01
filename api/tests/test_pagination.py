from __future__ import annotations

import asyncio
from typing import Any

from app.services.libraries import LibrariesService
from app.services.tags import TagsService


class RecordingReactor:
    """Captures Reactor GET params so pagination regressions are caught in CI."""

    def __init__(self, *, list_payload: dict[str, Any] | None = None):
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self._list_payload = list_payload or {
            "data": [],
            "meta": {"pagination": {"total_count": 0}},
        }

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((path, params))
        if path == "/companies":
            return {"data": [{"id": "CO1", "type": "companies"}]}
        return self._list_payload


def test_list_published_libraries_sends_one_based_page_number() -> None:
    reactor = RecordingReactor()
    service = LibrariesService(reactor, default_page_size=25, max_page_size=50)

    asyncio.run(
        service.list_published_libraries("PR1", page=2, page_size=25),
    )

    _, params = reactor.calls[0]
    assert params is not None
    assert params["page[number]"] == 2
    assert params["page[size]"] == 25


def test_list_rules_sends_one_based_page_number() -> None:
    reactor = RecordingReactor()
    service = TagsService(reactor, default_page_size=25, max_page_size=50)

    asyncio.run(service.list_rules("PR1", page=3, page_size=25))

    _, params = reactor.calls[0]
    assert params is not None
    assert params["page[number]"] == 3
    assert params["page[size]"] == 25
