from __future__ import annotations

import json

import pytest

from app.presenters.analysis import present_rule_dependencies
from app.presenters.common import (
    extract_data_element_reference_hits,
    extract_data_element_references,
)
from app.services.analysis import AnalysisService
from app.services.revisions import RevisionService


def test_extract_token_and_getvar_hits() -> None:
    settings = json.dumps(
        {
            "source": (
                "var a = _satellite.getVar(\"Page Name\");\n"
                "var b = _satellite.getVar('Campaign ID');\n"
                "var c = %Data Element: User Id%;\n"
            )
        }
    )
    hits = extract_data_element_reference_hits(settings)
    by_name = {hit["name"]: hit["detectionMethod"] for hit in hits}
    assert by_name["Page Name"] == "customCode"
    assert by_name["Campaign ID"] == "customCode"
    assert by_name["User Id"] == "token"
    assert extract_data_element_references(settings) == [
        "User Id",
        "Page Name",
        "Campaign ID",
    ]


def test_extract_token_wins_when_also_in_getvar() -> None:
    text = '%DE: Shared% and _satellite.getVar("Shared")'
    hits = extract_data_element_reference_hits(text)
    assert len(hits) == 1
    assert hits[0] == {"name": "Shared", "detectionMethod": "token"}


def test_extract_ignores_dynamic_getvar() -> None:
    text = "_satellite.getVar(variableName); _satellite.getVar(foo + 'bar');"
    assert extract_data_element_reference_hits(text) == []


def test_present_never_published_live_scope_narrative() -> None:
    view = present_rule_dependencies(
        rule={"id": "RL1", "name": "Draft Rule", "enabled": True, "version": 1},
        data_elements=[],
        extensions=[],
        unresolved_data_element_names=[],
        version_scope="live",
        version_context={
            "scannedRevision": None,
            "scannedRevisionId": None,
            "liveRevision": None,
            "liveRevisionId": None,
            "publishState": "neverPublished",
        },
        live_dependencies_available=False,
    )
    assert view["liveDependenciesAvailable"] is False
    assert "never been published" in view["narrative"]
    assert view["versionScope"] == "live"


class _FakeReactor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    async def get(self, path: str, params=None):
        self.calls.append((path, params))
        if path == "/rules/RL_HEAD":
            return {
                "data": {
                    "id": "RL_HEAD",
                    "type": "rules",
                    "attributes": {
                        "name": "Checkout",
                        "enabled": True,
                        "revision_number": 0,
                    },
                    "meta": {"latest_revision_number": 3},
                    "relationships": {
                        "property": {"data": {"id": "PR1", "type": "properties"}},
                    },
                }
            }
        if path == "/rules/RL_HEAD/revisions":
            return {
                "data": [
                    {
                        "id": "RL_LIVE",
                        "attributes": {
                            "name": "Checkout",
                            "enabled": True,
                            "revision_number": 2,
                            "published": True,
                            "published_at": "2026-01-02T00:00:00.000Z",
                        },
                    },
                    {
                        "id": "RL_OLD",
                        "attributes": {
                            "name": "Checkout",
                            "enabled": True,
                            "revision_number": 1,
                            "published": True,
                            "published_at": "2026-01-01T00:00:00.000Z",
                        },
                    },
                ]
            }
        if path == "/rules/RL_HEAD/rule_components":
            return {
                "data": [
                    {
                        "id": "RC_LATEST",
                        "attributes": {
                            "settings": json.dumps(
                                {
                                    "source": (
                                        '_satellite.getVar("Latest DE");'
                                        "%Data Element: Token DE%"
                                    )
                                }
                            )
                        },
                        "relationships": {
                            "extension": {"data": {"id": "EX1", "type": "extensions"}},
                        },
                    }
                ]
            }
        if path == "/rules/RL_LIVE/rule_components":
            return {
                "data": [
                    {
                        "id": "RC_LIVE",
                        "attributes": {
                            "settings": json.dumps(
                                {"source": '_satellite.getVar("Live Only DE");'}
                            )
                        },
                        "relationships": {
                            "extension": {"data": {"id": "EX1", "type": "extensions"}},
                        },
                    }
                ]
            }
        if path == "/properties/PR1/data_elements":
            return {
                "data": [
                    {
                        "id": "DE1",
                        "attributes": {"name": "Latest DE", "enabled": True},
                    },
                    {
                        "id": "DE2",
                        "attributes": {"name": "Token DE", "enabled": True},
                    },
                    {
                        "id": "DE3",
                        "attributes": {"name": "Live Only DE", "enabled": True},
                    },
                ]
            }
        if path == "/extensions/EX1":
            return {
                "data": {
                    "id": "EX1",
                    "attributes": {
                        "name": "Core",
                        "enabled": True,
                        "version": "1.2.3",
                    },
                }
            }
        raise AssertionError(f"Unexpected path: {path}")


class _NeverPublishedReactor(_FakeReactor):
    async def get(self, path: str, params=None):
        self.calls.append((path, params))
        if path == "/rules/RL_NEW":
            return {
                "data": {
                    "id": "RL_NEW",
                    "type": "rules",
                    "attributes": {
                        "name": "Brand New",
                        "enabled": True,
                        "revision_number": 0,
                        "published": False,
                    },
                    "meta": {"latest_revision_number": 1},
                    "relationships": {
                        "property": {"data": {"id": "PR1", "type": "properties"}},
                    },
                }
            }
        if path == "/rules/RL_NEW/revisions":
            return {
                "data": [
                    {
                        "id": "RL_NEW_R1",
                        "attributes": {
                            "name": "Brand New",
                            "enabled": True,
                            "revision_number": 1,
                            "published": False,
                        },
                    }
                ]
            }
        raise AssertionError(f"Unexpected path: {path}")


@pytest.mark.asyncio
async def test_dependencies_latest_detects_getvar_and_token() -> None:
    reactor = _FakeReactor()
    service = AnalysisService(
        reactor,  # type: ignore[arg-type]
        revision_service=RevisionService(reactor),  # type: ignore[arg-type]
    )
    view = await service.get_rule_dependencies("RL_HEAD", version_scope="latest")

    assert view["versionScope"] == "latest"
    assert view["versionContext"] == {
        "scannedRevision": 3,
        "scannedRevisionId": "RL_HEAD",
        "liveRevision": 2,
        "liveRevisionId": "RL_LIVE",
        "publishState": "modified",
    }
    assert view["liveDependenciesAvailable"] is True
    assert "published" not in view["versionContext"]
    assert "publishedAt" not in view["versionContext"]
    assert "liveResolutionMethod" not in view["versionContext"]
    assert "enabled" not in view["versionContext"]

    de_by_name = {item["name"]: item for item in view["dataElements"]}
    assert de_by_name["Latest DE"]["detectionMethod"] == "customCode"
    assert de_by_name["Token DE"]["detectionMethod"] == "token"
    assert view["extensions"][0]["id"] == "EX1"
    assert any(path == "/rules/RL_HEAD/rule_components" for path, _ in reactor.calls)


@pytest.mark.asyncio
async def test_dependencies_live_scans_live_revision_components() -> None:
    reactor = _FakeReactor()
    service = AnalysisService(
        reactor,  # type: ignore[arg-type]
        revision_service=RevisionService(reactor),  # type: ignore[arg-type]
    )
    view = await service.get_rule_dependencies("RL_HEAD", version_scope="live")

    assert view["versionScope"] == "live"
    assert view["versionContext"]["scannedRevisionId"] == "RL_LIVE"
    assert view["versionContext"]["scannedRevision"] == 2
    assert view["rule"]["id"] == "RL_LIVE"
    assert view["rule"]["version"] == 2
    assert [item["name"] for item in view["dataElements"]] == ["Live Only DE"]
    assert view["dataElements"][0]["detectionMethod"] == "customCode"
    assert any(path == "/rules/RL_LIVE/rule_components" for path, _ in reactor.calls)
    assert not any(path == "/rules/RL_HEAD/rule_components" for path, _ in reactor.calls)


@pytest.mark.asyncio
async def test_dependencies_live_never_published_returns_empty() -> None:
    reactor = _NeverPublishedReactor()
    service = AnalysisService(
        reactor,  # type: ignore[arg-type]
        revision_service=RevisionService(reactor),  # type: ignore[arg-type]
    )
    view = await service.get_rule_dependencies("RL_NEW", version_scope="live")

    assert view["liveDependenciesAvailable"] is False
    assert view["dataElements"] == []
    assert view["extensions"] == []
    assert view["versionContext"]["publishState"] == "neverPublished"
    assert "never been published" in view["narrative"]
    assert not any("rule_components" in path for path, _ in reactor.calls)
