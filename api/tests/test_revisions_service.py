from __future__ import annotations

import pytest

from app.adobe.revision_logic import derive_publish_state, latest_version_number
from app.services.revisions import RevisionService


class FakeReactor:
    def __init__(self, *, resources: dict[str, dict], revisions_by_id: dict[str, list[dict]]):
        self._resources = resources
        self._revisions_by_id = revisions_by_id
        self.head_calls = 0
        self.revision_calls = 0

    async def get(self, path: str, params=None):
        if path.endswith("/revisions"):
            self.revision_calls += 1
            resource_id = path.rsplit("/", 2)[1]
            return {"data": self._revisions_by_id.get(resource_id, [])}
        self.head_calls += 1
        resource_id = path.rsplit("/", 1)[-1]
        item = self._resources[resource_id]
        return {"data": item, "meta": item.get("meta") or {}}


@pytest.mark.asyncio
async def test_resolve_versions_uses_passed_head_without_refetch() -> None:
    head = {
        "id": "RL_HEAD",
        "attributes": {"name": "Rule A", "enabled": True, "revision_number": 0},
        "meta": {"latest_revision_number": 2},
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    revisions = [
        {"id": "RL1", "attributes": {"revision_number": 1, "published": True, "published_at": "2026-01-01"}},
        {"id": "RL2", "attributes": {"revision_number": 2, "published": True, "published_at": "2026-01-02"}},
    ]
    reactor = FakeReactor(
        resources={"RL_HEAD": head},
        revisions_by_id={"RL_HEAD": revisions},
    )
    service = RevisionService(reactor)  # type: ignore[arg-type]

    resolved = await service.resolve_versions("rules", "RL_HEAD", head_item=head)

    assert reactor.head_calls == 0
    assert resolved.latest_version == 2
    assert resolved.publish_state == "live"
    assert resolved.version_summary["latest"]["id"] == "RL_HEAD"
    assert resolved.version_summary["latest"]["version"] == 2


@pytest.mark.asyncio
async def test_resolve_versions_modified_when_head_meta_ahead_of_live() -> None:
    head = {
        "id": "RL_HEAD",
        "attributes": {"name": "Rule A", "enabled": True, "revision_number": 0},
        "meta": {"latest_revision_number": 3},
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    revisions = [
        {"id": "RL1", "attributes": {"revision_number": 1, "published": True, "published_at": "2026-01-01"}},
        {"id": "RL2", "attributes": {"revision_number": 2, "published": True, "published_at": "2026-01-02"}},
    ]
    reactor = FakeReactor(
        resources={"RL_HEAD": head},
        revisions_by_id={"RL_HEAD": revisions},
    )
    service = RevisionService(reactor)  # type: ignore[arg-type]

    resolved = await service.resolve_versions("rules", "RL_HEAD", head_item=head)

    assert resolved.publish_state == "modified"
    assert latest_version_number(head, revisions) == 3
    assert derive_publish_state(head, resolved.live_item, revisions) == "modified"


@pytest.mark.asyncio
async def test_resolve_versions_canonicalizes_live_revision_id() -> None:
    """Passing a live revision id must not treat it as head (same id, wrong version)."""
    head = {
        "id": "RL_HEAD",
        "attributes": {"name": "Rule A", "enabled": True, "revision_number": 0},
        "meta": {"latest_revision_number": 4},
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    live = {
        "id": "RL_LIVE",
        "attributes": {
            "name": "Rule A",
            "enabled": True,
            "revision_number": 3,
            "published": True,
            "published_at": "2026-01-02",
        },
        "meta": {"latest_revision_number": 4},
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    revisions = [
        {
            "id": "RL_LIVE",
            "attributes": {
                "revision_number": 3,
                "published": True,
                "published_at": "2026-01-02",
                "enabled": True,
            },
        },
        {
            "id": "RL_OLD",
            "attributes": {
                "revision_number": 2,
                "published": True,
                "published_at": "2026-01-01",
                "enabled": True,
            },
        },
    ]
    reactor = FakeReactor(
        resources={"RL_HEAD": head, "RL_LIVE": live},
        revisions_by_id={"RL_HEAD": revisions, "RL_LIVE": revisions},
    )
    service = RevisionService(reactor)  # type: ignore[arg-type]

    resolved = await service.resolve_versions("rules", "RL_LIVE", head_item=live)
    summary = resolved.version_summary

    assert resolved.head_item["id"] == "RL_HEAD"
    assert resolved.latest_version == 4
    assert resolved.publish_state == "modified"
    assert summary["latest"]["id"] == "RL_HEAD"
    assert summary["latest"]["version"] == 4
    assert summary["live"]["id"] == "RL_LIVE"
    assert summary["live"]["version"] == 3
    assert summary["latest"]["id"] != summary["live"]["id"]
    assert resolved.version_for_item(live) == 3
    assert resolved.version_for_item(head) == 4
    assert resolved.published_for_item(live) is True
    assert resolved.published_for_item(head) is False


@pytest.mark.asyncio
async def test_version_for_item_ignores_family_meta_on_revision_get() -> None:
    """Adobe may attach meta.latest_revision_number=4 on a v3 revision GET payload."""
    head = {
        "id": "RL_HEAD",
        "attributes": {"name": "Rule A", "enabled": True, "revision_number": 0},
        "meta": {"latest_revision_number": 4},
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    live_get_payload = {
        "id": "RL_LIVE",
        "attributes": {
            "name": "Rule A",
            "enabled": True,
            # Some payloads omit or zero revision_number on direct GET
            "revision_number": 0,
            "published": True,
            "published_at": "2026-01-02",
        },
        "meta": {"latest_revision_number": 4},
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    revisions = [
        {
            "id": "RL_LIVE",
            "attributes": {
                "revision_number": 3,
                "published": True,
                "published_at": "2026-01-02",
                "enabled": True,
            },
        }
    ]
    reactor = FakeReactor(
        resources={"RL_HEAD": head, "RL_LIVE": live_get_payload},
        revisions_by_id={"RL_HEAD": revisions},
    )
    service = RevisionService(reactor)  # type: ignore[arg-type]
    resolved = await service.resolve_versions("rules", "RL_LIVE", head_item=live_get_payload)
    assert resolved.version_for_item(live_get_payload) == 3
    assert resolved.published_for_item(live_get_payload) is True


@pytest.mark.asyncio
async def test_published_for_item_matches_revision_deploy_semantics() -> None:
    """v3 live → published true; v4 pending head → false; older deployed v2 → true."""
    head = {
        "id": "RL_HEAD",
        "attributes": {
            "name": "Rule A",
            "enabled": True,
            "revision_number": 0,
            # Adobe often marks head published=true even when latest is only a draft.
            "published": True,
        },
        "meta": {"latest_revision_number": 4},
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    live = {
        "id": "RL_V3",
        "attributes": {
            "revision_number": 3,
            "published": True,
            "published_at": "2026-02-01",
            "enabled": True,
        },
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    pending = {
        "id": "RL_V4",
        "attributes": {
            "revision_number": 4,
            "published": False,
            "enabled": True,
        },
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    older = {
        "id": "RL_V2",
        "attributes": {
            "revision_number": 2,
            "published": True,
            "published_at": "2026-01-01",
            "enabled": True,
        },
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    revisions = [live, older, pending]
    reactor = FakeReactor(
        resources={
            "RL_HEAD": head,
            "RL_V3": live,
            "RL_V4": pending,
            "RL_V2": older,
        },
        revisions_by_id={"RL_HEAD": revisions},
    )
    service = RevisionService(reactor)  # type: ignore[arg-type]

    resolved_head = await service.resolve_versions("rules", "RL_HEAD", head_item=head)
    assert resolved_head.publish_state == "modified"
    assert resolved_head.published_for_item(head) is False

    resolved_live = await service.resolve_versions("rules", "RL_V3", head_item=live)
    assert resolved_live.published_for_item(live) is True

    resolved_pending = await service.resolve_versions("rules", "RL_V4", head_item=pending)
    assert resolved_pending.published_for_item(pending) is False

    resolved_older = await service.resolve_versions("rules", "RL_V2", head_item=older)
    assert resolved_older.published_for_item(older) is True


class FakeReactorWithLibraries(FakeReactor):
    def __init__(
        self,
        *,
        resources: dict[str, dict],
        revisions_by_id: dict[str, list[dict]],
        libraries: list[dict] | None = None,
        library_members: dict[str, list[dict]] | None = None,
    ):
        super().__init__(resources=resources, revisions_by_id=revisions_by_id)
        self._libraries = libraries or []
        self._library_members = library_members or {}

    async def get(self, path: str, params=None):
        if path.endswith("/libraries") and "/properties/" in path:
            return {"data": self._libraries, "meta": {"pagination": {"next_page": None}}}
        if "/libraries/" in path and path.endswith("/rules"):
            library_id = path.rsplit("/", 2)[1]
            return {
                "data": self._library_members.get(library_id, []),
                "meta": {"pagination": {"next_page": None}},
            }
        return await super().get(path, params)


@pytest.mark.asyncio
async def test_list_revision_history_defaults_to_important_view() -> None:
    head = {
        "id": "RL_HEAD",
        "attributes": {"name": "Rule A", "enabled": True, "revision_number": 0},
        "meta": {"latest_revision_number": 3},
        "relationships": {
            "origin": {"data": {"id": "RL_HEAD", "type": "rules"}},
            "property": {"data": {"id": "PR1", "type": "properties"}},
        },
    }
    live = {
        "id": "RL_V1",
        "attributes": {
            "revision_number": 1,
            "published": True,
            "published_at": "2026-01-01",
            "enabled": True,
        },
    }
    noise = {"id": "RL_V2", "attributes": {"revision_number": 2, "enabled": True}}
    in_lib = {"id": "RL_V3", "attributes": {"revision_number": 3, "enabled": True}}
    reactor = FakeReactorWithLibraries(
        resources={"RL_HEAD": head},
        revisions_by_id={"RL_HEAD": [live, noise, in_lib]},
        libraries=[{"id": "LB1", "attributes": {"state": "development"}}],
        library_members={"LB1": [in_lib]},
    )
    service = RevisionService(reactor)  # type: ignore[arg-type]

    important = await service.list_rule_revisions("RL_HEAD")
    assert important["view"] == "important"
    assert important["importantCount"] == 3
    assert important["fullRevisionCount"] == 4
    assert [row["id"] for row in important["revisions"]] == ["RL_HEAD", "RL_V3", "RL_V1"]

    full = await service.list_rule_revisions("RL_HEAD", view="full")
    assert full["view"] == "full"
    assert full["totalCount"] == 4
    by_id = {row["id"]: row for row in full["revisions"]}
    assert by_id["RL_V2"]["important"] is False
