from __future__ import annotations

import json

import pytest

from app.presenters.usage import present_usage_search
from app.services.revisions import RevisionService
from app.services.usage import UsageService, UsageServiceError


def test_present_usage_narrative_mentions_live_scope() -> None:
    view = present_usage_search(
        property_id="PR1",
        query="Page Name",
        version_scope="live",
        status="ok",
        detail="summary",
        matched_data_element={"id": "DE1", "name": "Page Name", "enabled": True},
        consumers=[
            {"resourceType": "rule", "id": "RL_LIVE", "name": "Rule A"},
            {"resourceType": "dataElement", "id": "DE2", "name": "Wrapper"},
        ],
    )
    assert view["status"] == "ok"
    assert "live (production)" in view["narrative"]
    assert "1 rule(s)" in view["narrative"]
    assert "1 data element(s)" in view["narrative"]
    assert view["consumerCount"] == 2


def test_present_hits_narrative() -> None:
    view = present_usage_search(
        property_id="PR1",
        query="_satellite.buildInfo",
        version_scope="latest",
        status="ok",
        mode="freeText",
        detail="hits",
        hits=[
            {"resourceType": "extension", "id": "EX1", "name": "Adobe Analytics"},
            {"resourceType": "ruleComponent", "id": "RC1", "name": "Custom code"},
        ],
    )
    assert view["hitCount"] == 2
    assert "High-level search" in view["narrative"]
    assert "1 extension" in view["narrative"]
    assert "get_rule" in view["narrative"]


def test_present_disambiguation_does_not_claim_scan() -> None:
    view = present_usage_search(
        property_id="PR1",
        query="Shared",
        version_scope="latest",
        status="needsDisambiguation",
        matches=[
            {"id": "DE1", "name": "Shared", "enabled": True},
            {"id": "DE2", "name": "Shared", "enabled": False},
        ],
    )
    assert "No usage scan was run" in view["narrative"]
    assert len(view["matches"]) == 2


def test_present_free_text_narrative() -> None:
    view = present_usage_search(
        property_id="PR1",
        query="eVar7",
        version_scope="live",
        status="ok",
        mode="freeText",
        detail="summary",
        consumers=[{"resourceType": "rule", "id": "RL1", "name": "A"}],
    )
    assert "Free-text search" in view["narrative"]
    assert "eVar7" in view["narrative"]


class _FakeReactor:
    def __init__(
        self,
        *,
        data_elements: list[dict],
        search_by_type: dict[str, list[dict]] | None = None,
        component_rules: dict[str, list[dict]] | None = None,
        resources: dict[str, dict] | None = None,
        revisions_by_id: dict[str, list[dict]] | None = None,
        rule_components: dict[str, list[dict]] | None = None,
    ):
        self._data_elements = data_elements
        self._search_by_type = search_by_type or {}
        self._component_rules = component_rules or {}
        self._resources = resources or {}
        self._revisions_by_id = revisions_by_id or {}
        self._rule_components = rule_components or {}
        self.search_bodies: list[dict] = []

    async def search(self, query: dict):
        self.search_bodies.append(query)
        types = query.get("resource_types") or []
        items: list[dict] = []
        for resource_type in types:
            items.extend(self._search_by_type.get(resource_type, []))
        if query.get("from", 0) > 0:
            items = []
        return {"data": items, "meta": {"total_hits": len(items)}}

    async def get(self, path: str, params=None):
        if path.endswith("/data_elements") and "/properties/" in path:
            return {
                "data": self._data_elements,
                "meta": {"pagination": {"next_page": None}},
            }
        if path.startswith("/rules/") and path.endswith("/rule_components"):
            rule_id = path.split("/")[2]
            return {
                "data": self._rule_components.get(rule_id, []),
                "meta": {"pagination": {"next_page": None}},
            }
        if path.startswith("/rule_components/") and path.endswith("/rules"):
            component_id = path.split("/")[2]
            return {"data": self._component_rules.get(component_id, [])}
        if path.endswith("/revisions"):
            resource_id = path.rsplit("/", 2)[1]
            return {"data": self._revisions_by_id.get(resource_id, [])}
        resource_id = path.rsplit("/", 1)[-1]
        item = self._resources[resource_id]
        return {"data": item, "meta": item.get("meta") or {}}


def _de(de_id: str, name: str, *, settings: str | None = None, **attrs) -> dict:
    attributes = {"name": name, "enabled": True, "revision_number": 0, **attrs}
    if settings is not None:
        attributes["settings"] = settings
    return {
        "id": de_id,
        "type": "data_elements",
        "attributes": attributes,
        "relationships": {"origin": {"data": {"id": de_id, "type": "data_elements"}}},
    }


def _component(rc_id: str, settings: str, *, name: str = "Action") -> dict:
    return {
        "id": rc_id,
        "type": "rule_components",
        "attributes": {
            "settings": settings,
            "name": name,
            "revision_number": 1,
            "delegate_descriptor_id": "core::actions::custom-code",
        },
    }


@pytest.mark.asyncio
async def test_find_usage_disambiguates_duplicate_names() -> None:
    reactor = _FakeReactor(
        data_elements=[_de("DE1", "Shared"), _de("DE2", "Shared")],
    )
    service = UsageService(reactor, revision_service=RevisionService(reactor))  # type: ignore[arg-type]
    result = await service.find_usage(
        "PR1", query="Shared", version_scope="latest", mode="dataElement"
    )
    assert result["status"] == "needsDisambiguation"
    assert len(result["matches"]) == 2
    assert reactor.search_bodies == []


@pytest.mark.asyncio
async def test_find_usage_default_hits_is_fast_and_combined() -> None:
    settings = json.dumps({"code": "_satellite.buildInfo.buildDate"})
    extension = {
        "id": "EX1",
        "type": "extensions",
        "attributes": {
            "display_name": "Adobe Analytics",
            "name": "adobe-analytics",
            "enabled": True,
            "revision_number": 0,
            "settings": settings,
            "published": False,
        },
        "relationships": {"origin": {"data": {"id": "EX1", "type": "extensions"}}},
    }
    component = _component("RC1", settings, name="Custom code")
    reactor = _FakeReactor(
        data_elements=[],
        search_by_type={
            "rule_components": [component],
            "data_elements": [],
            "extensions": [extension],
        },
        # If enrichment ran, these would be consulted — hits path must not need them.
        component_rules={},
        resources={},
    )
    service = UsageService(reactor, revision_service=RevisionService(reactor))  # type: ignore[arg-type]
    result = await service.find_usage(
        "PR1",
        query="_satellite.buildInfo",
        mode="freeText",
    )
    assert result["status"] == "ok"
    assert result["detail"] == "hits"
    assert result["versionScope"] == "latest"
    assert result["hitCount"] == 2
    assert {row["resourceType"] for row in result["hits"]} == {"ruleComponent", "extension"}
    assert "consumers" not in result
    assert len(reactor.search_bodies) == 1
    body = reactor.search_bodies[0]
    assert set(body["resource_types"]) == {
        "rule_components",
        "data_elements",
        "extensions",
    }
    assert body["query"]["attributes.revision_number"] == {"value": 0}
    assert "High-level search" in result["narrative"]


@pytest.mark.asyncio
async def test_find_usage_live_rules_and_data_elements() -> None:
    settings = json.dumps({"source": '%Data Element: Page Name%'})
    head = {
        "id": "RL_HEAD",
        "type": "rules",
        "attributes": {"name": "Checkout", "enabled": True, "revision_number": 0},
        "meta": {"latest_revision_number": 2},
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    live = {
        "id": "RL_LIVE",
        "type": "rules",
        "attributes": {
            "name": "Checkout",
            "enabled": True,
            "revision_number": 1,
            "published": True,
            "published_at": "2026-01-01",
        },
        "meta": {"latest_revision_number": 2},
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    wrapper_head = {
        "id": "DE_WRAP",
        "type": "data_elements",
        "attributes": {
            "name": "Page Name Wrapper",
            "enabled": True,
            "revision_number": 0,
            "settings": settings,
        },
        "meta": {"latest_revision_number": 1},
        "relationships": {"origin": {"data": {"id": "DE_WRAP", "type": "data_elements"}}},
    }
    wrapper_live = {
        "id": "DE_WRAP_LIVE",
        "type": "data_elements",
        "attributes": {
            "name": "Page Name Wrapper",
            "enabled": True,
            "revision_number": 1,
            "published": True,
            "published_at": "2026-01-01",
            "settings": settings,
        },
        "meta": {"latest_revision_number": 1},
        "relationships": {"origin": {"data": {"id": "DE_WRAP", "type": "data_elements"}}},
    }
    target = _de("DE1", "Page Name")

    reactor = _FakeReactor(
        data_elements=[target, wrapper_head],
        search_by_type={
            "rule_components": [
                _component("RC_LIVE", settings),
                _component("RC_LATEST", settings),
                _component("RC_NOISE", json.dumps({"note": "Page Name mentioned loosely"})),
            ],
            "data_elements": [wrapper_live, target],
        },
        component_rules={
            "RC_LIVE": [live],
            "RC_LATEST": [head],
            "RC_NOISE": [live],
        },
        resources={
            "RL_HEAD": head,
            "RL_LIVE": live,
            "DE1": target,
            "DE_WRAP": wrapper_head,
            "DE_WRAP_LIVE": wrapper_live,
        },
        revisions_by_id={
            "RL_HEAD": [
                {
                    "id": "RL_LIVE",
                    "attributes": {
                        "revision_number": 1,
                        "published": True,
                        "published_at": "2026-01-01",
                        "enabled": True,
                    },
                },
                {"id": "RL_PENDING", "attributes": {"revision_number": 2, "enabled": True}},
            ],
            "DE_WRAP": [
                {
                    "id": "DE_WRAP_LIVE",
                    "attributes": {
                        "revision_number": 1,
                        "published": True,
                        "published_at": "2026-01-01",
                        "enabled": True,
                        "settings": settings,
                    },
                }
            ],
            "DE1": [],
        },
    )
    service = UsageService(reactor, revision_service=RevisionService(reactor))  # type: ignore[arg-type]

    live_result = await service.find_usage(
        "PR1",
        query="Page Name",
        version_scope="live",
        mode="dataElement",
        detail="summary",
    )
    assert live_result["status"] == "ok"
    assert "live (production)" in live_result["narrative"]
    by_type = {row["resourceType"]: row for row in live_result["consumers"]}
    assert set(by_type) == {"rule", "dataElement"}
    assert by_type["rule"]["id"] == "RL_LIVE"
    assert by_type["dataElement"]["id"] == "DE_WRAP_LIVE"
    # Target DE itself must not appear as a consumer.
    assert all(row.get("headId") != "DE1" for row in live_result["consumers"])
    assert live_result["searchHitsVerified"] == 3  # 2 verified components + wrapper DE

    detailed = await service.find_usage(
        "PR1",
        query="Page Name",
        version_scope="live",
        mode="dataElement",
        detail="components",
    )
    rule = next(row for row in detailed["consumers"] if row["resourceType"] == "rule")
    assert rule["componentCount"] == 1
    assert rule["components"][0]["id"] == "RC_LIVE"
    assert rule["components"][0]["componentKind"] == "actions"


@pytest.mark.asyncio
async def test_find_usage_free_text_mode() -> None:
    settings = json.dumps({"evar": "eVar7", "note": "maps to eVar7"})
    head = {
        "id": "RL_HEAD",
        "type": "rules",
        "attributes": {"name": "Analytics", "enabled": True, "revision_number": 0},
        "meta": {"latest_revision_number": 1},
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    live = {
        "id": "RL_LIVE",
        "type": "rules",
        "attributes": {
            "name": "Analytics",
            "enabled": True,
            "revision_number": 1,
            "published": True,
            "published_at": "2026-01-01",
        },
        "meta": {"latest_revision_number": 1},
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    reactor = _FakeReactor(
        data_elements=[],
        search_by_type={
            "rule_components": [_component("RC1", settings, name="Set vars")],
            "data_elements": [],
        },
        component_rules={"RC1": [live]},
        resources={"RL_HEAD": head, "RL_LIVE": live},
        revisions_by_id={
            "RL_HEAD": [
                {
                    "id": "RL_LIVE",
                    "attributes": {
                        "revision_number": 1,
                        "published": True,
                        "published_at": "2026-01-01",
                        "enabled": True,
                    },
                }
            ]
        },
    )
    service = UsageService(reactor, revision_service=RevisionService(reactor))  # type: ignore[arg-type]
    result = await service.find_usage(
        "PR1",
        query="eVar7",
        version_scope="live",
        mode="freeText",
        detail="components",
    )
    assert result["mode"] == "freeText"
    assert result["status"] == "ok"
    assert "Free-text search" in result["narrative"]
    assert result["consumerCount"] == 1
    assert result["consumers"][0]["detectionMethod"] == "settingsText"
    assert result["consumers"][0]["components"][0]["name"] == "Set vars"
    # freeText does not require DE list resolution first
    assert result.get("matchedDataElement") is None


@pytest.mark.asyncio
async def test_find_usage_confirms_live_when_search_only_returns_older_revision() -> None:
    """Search may index an old revision; live scope should confirm the live rule components."""
    settings = json.dumps({"source": '%DE: Page Name%'})
    head = {
        "id": "RL_HEAD",
        "type": "rules",
        "attributes": {"name": "Checkout", "enabled": True, "revision_number": 0},
        "meta": {"latest_revision_number": 2},
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    live = {
        "id": "RL_LIVE",
        "type": "rules",
        "attributes": {
            "name": "Checkout",
            "enabled": True,
            "revision_number": 1,
            "published": True,
            "published_at": "2026-01-01",
        },
        "meta": {"latest_revision_number": 2},
        "relationships": {"origin": {"data": {"id": "RL_HEAD", "type": "rules"}}},
    }
    old_component = _component("RC_OLD", settings)
    live_component = _component("RC_LIVE", settings, name="Live action")
    reactor = _FakeReactor(
        data_elements=[_de("DE1", "Page Name")],
        search_by_type={
            # Only an older head-linked component is in search results
            "rule_components": [old_component],
            "data_elements": [],
        },
        component_rules={"RC_OLD": [head]},
        resources={"RL_HEAD": head, "RL_LIVE": live},
        revisions_by_id={
            "RL_HEAD": [
                {
                    "id": "RL_LIVE",
                    "attributes": {
                        "revision_number": 1,
                        "published": True,
                        "published_at": "2026-01-01",
                        "enabled": True,
                    },
                }
            ]
        },
        rule_components={"RL_LIVE": [live_component]},
    )
    service = UsageService(reactor, revision_service=RevisionService(reactor))  # type: ignore[arg-type]
    result = await service.find_usage(
        "PR1",
        query="Page Name",
        version_scope="live",
        mode="dataElement",
        detail="components",
    )
    assert result["consumerCount"] == 1
    assert result["consumers"][0]["id"] == "RL_LIVE"
    assert result["consumers"][0]["components"][0]["id"] == "RC_LIVE"


@pytest.mark.asyncio
async def test_find_usage_free_text_finds_extension_settings() -> None:
    settings = json.dumps(
        {"libraryCode": {"code": "s.eVar1 = _satellite.buildInfo.buildDate;"}}
    )
    head = {
        "id": "EX_HEAD",
        "type": "extensions",
        "attributes": {
            "display_name": "Adobe Analytics",
            "name": "adobe-analytics",
            "enabled": True,
            "revision_number": 0,
            "settings": settings,
        },
        "meta": {"latest_revision_number": 1},
        "relationships": {"origin": {"data": {"id": "EX_HEAD", "type": "extensions"}}},
    }
    live = {
        "id": "EX_LIVE",
        "type": "extensions",
        "attributes": {
            "display_name": "Adobe Analytics",
            "name": "adobe-analytics",
            "enabled": True,
            "revision_number": 1,
            "published": True,
            "published_at": "2026-01-01",
            "settings": settings,
        },
        "meta": {"latest_revision_number": 1},
        "relationships": {"origin": {"data": {"id": "EX_HEAD", "type": "extensions"}}},
    }
    reactor = _FakeReactor(
        data_elements=[],
        search_by_type={
            "rule_components": [],
            "data_elements": [],
            "extensions": [live],
        },
        resources={"EX_HEAD": head, "EX_LIVE": live},
        revisions_by_id={
            "EX_HEAD": [
                {
                    "id": "EX_LIVE",
                    "attributes": {
                        "revision_number": 1,
                        "published": True,
                        "published_at": "2026-01-01",
                        "enabled": True,
                        "settings": settings,
                    },
                }
            ]
        },
    )
    service = UsageService(reactor, revision_service=RevisionService(reactor))  # type: ignore[arg-type]
    result = await service.find_usage(
        "PR1",
        query="_satellite.buildInfo",
        version_scope="live",
        mode="freeText",
        detail="summary",
    )
    assert result["consumerCount"] == 1
    assert result["consumers"][0]["resourceType"] == "extension"
    assert result["consumers"][0]["id"] == "EX_LIVE"
    assert "1 extension(s)" in result["narrative"]


@pytest.mark.asyncio
async def test_find_usage_auto_falls_back_to_free_text_when_de_missing() -> None:
    settings = json.dumps({"obj": "MWPAPI", "path": "MWPAPI.foo"})
    component = _component("RC1", settings)
    reactor = _FakeReactor(
        data_elements=[],
        search_by_type={
            "rule_components": [component],
            "data_elements": [],
        },
    )
    service = UsageService(reactor, revision_service=RevisionService(reactor))  # type: ignore[arg-type]
    result = await service.find_usage("PR1", query="MWPAPI", mode="dataElement")
    assert result["autoSwitchedToFreeText"] is True
    assert result["mode"] == "freeText"
    assert result["detail"] == "hits"
    assert result["hitCount"] == 1
    assert result["hits"][0]["resourceType"] == "ruleComponent"


@pytest.mark.asyncio
async def test_find_usage_default_mode_is_free_text() -> None:
    settings = json.dumps({"obj": "gamename"})
    reactor = _FakeReactor(
        data_elements=[_de("DE1", "Unrelated")],
        search_by_type={
            "rule_components": [_component("RC1", settings)],
            "data_elements": [],
        },
    )
    service = UsageService(reactor, revision_service=RevisionService(reactor))  # type: ignore[arg-type]
    result = await service.find_usage("PR1", query="gamename")
    assert result["mode"] == "freeText"
    assert result.get("autoSwitchedToFreeText") is None
    assert result["hitCount"] == 1
    # Default freeText does not resolve data elements first.
    assert reactor.search_bodies
    assert result.get("matchedDataElement") is None


@pytest.mark.asyncio
async def test_find_usage_rejects_empty_query() -> None:
    reactor = _FakeReactor(data_elements=[])
    service = UsageService(reactor, revision_service=RevisionService(reactor))  # type: ignore[arg-type]
    with pytest.raises(UsageServiceError) as exc:
        await service.find_usage("PR1", query="  ")
    assert exc.value.code == "INVALID_QUERY"
