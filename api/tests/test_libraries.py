from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.auth.session_store import SessionStore
from app.presenters.library import (
    classify_dev_library_change,
    present_ambiguous_libraries,
    present_development_library_review,
    present_library_index,
    present_library_resource_row,
)
from app.services.libraries import LibrariesService
from app.services.revisions import RevisionService
from app.services.session_manager import SessionManager


def test_present_library_resource_row_change_kind() -> None:
    item = {
        "id": "RL1",
        "attributes": {
            "name": "My Rule",
            "enabled": True,
            "dirty": True,
            "published": False,
        },
    }
    row = present_library_resource_row(item, resource_type="rule", version=2)
    assert row["version"] == 2
    assert row["changeKind"] == "modified"


def test_present_library_resource_row_new_resource() -> None:
    item = {
        "id": "RL2",
        "attributes": {
            "name": "New Rule",
            "dirty": False,
            "published": None,
            "revision_number": 0,
        },
    }
    row = present_library_resource_row(item, resource_type="rule", version=0)
    assert row["changeKind"] == "added"


def test_present_library_resource_row_new_resource_published_null() -> None:
    item = {
        "id": "RL3",
        "attributes": {
            "name": "Brand New",
            "published": None,
            "revision_number": 0,
        },
    }
    row = present_library_resource_row(item, resource_type="rule", version=0)
    assert row["changeKind"] == "added"


def test_present_library_index_published_date() -> None:
    published = present_library_index(
        {
            "id": "LB1",
            "attributes": {
                "name": "Prod",
                "state": "published",
                "published_at": "2026-01-01T00:00:00.000Z",
                "updated_at": "2026-01-02T00:00:00.000Z",
            },
        }
    )
    assert published["publishedAt"] == "2026-01-01T00:00:00.000Z"
    assert "updatedAt" not in published
    assert "meta" not in published

    dev = present_library_index(
        {
            "id": "LB2",
            "attributes": {
                "name": "Dev",
                "state": "development",
                "updated_at": "2026-02-01T00:00:00.000Z",
            },
        }
    )
    assert dev["updatedAt"] == "2026-02-01T00:00:00.000Z"
    assert "publishedAt" not in dev


def test_present_ambiguous_libraries() -> None:
    result = present_ambiguous_libraries(
        message="Pick one",
        candidates=[{"id": "LB1", "name": "Dev A"}, {"id": "LB2", "name": "Dev B"}],
    )
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 2


def test_classify_dev_library_change_kinds() -> None:
    live = {"id": "RL_LIVE", "attributes": {"enabled": True, "revision_number": 2}}
    pending_new = {"id": "RL_NEW", "attributes": {"enabled": True, "revision_number": 1}}
    pending_mod = {"id": "RL_PEND", "attributes": {"enabled": True, "revision_number": 3}}
    pending_disabled = {"id": "RL_OFF", "attributes": {"enabled": False, "revision_number": 3}}

    assert classify_dev_library_change(live_item=None, pending_item=pending_new) == "new"
    assert classify_dev_library_change(live_item=live, pending_item=pending_mod) == "modified"
    assert classify_dev_library_change(live_item=live, pending_item=pending_disabled) == "disabled"
    assert classify_dev_library_change(live_item=live, pending_item=live) is None


def test_present_development_library_review_summary() -> None:
    view = present_development_library_review(
        library={"id": "LB1", "name": "Dev"},
        depth="summary",
        changes={
            "rules": [
                {
                    "changeKind": "new",
                    "resourceKind": "rule",
                    "name": "New Rule",
                    "pending": {"id": "RL1", "version": 1, "enabled": True},
                },
                {
                    "changeKind": "disabled",
                    "resourceKind": "rule",
                    "name": "Old Rule",
                    "pending": {"id": "RL2b", "version": 3, "enabled": False},
                    "publishedLive": {"id": "RL2a", "version": 2, "enabled": True},
                },
            ],
            "dataElements": [
                {
                    "changeKind": "modified",
                    "resourceKind": "dataElement",
                    "name": "Page Name",
                    "pending": {"id": "DE1b", "version": 2, "enabled": True},
                    "publishedLive": {"id": "DE1a", "version": 1, "enabled": True},
                }
            ],
            "extensions": [],
        },
    )
    assert view["resourceType"] == "developmentLibraryReview"
    assert view["summary"]["new"] == 1
    assert view["summary"]["modified"] == 1
    assert view["summary"]["disabled"] == 1
    assert view["summary"]["totalChanges"] == 3
    assert "disabled" in view["narrative"]
    assert "pending.id" in view["narrative"]
    assert "pending" in view["idUsage"]
    assert "publishedLive" in view["idUsage"]
    assert all("headId" not in row for row in view["changes"]["rules"])
    assert all("headId" not in row for row in view["changes"]["dataElements"])


class _DevReviewReactor:
    async def get(self, path: str, params=None):
        if path == "/libraries/LB_DEV":
            return {
                "data": {
                    "id": "LB_DEV",
                    "type": "libraries",
                    "attributes": {"name": "Dev Lib", "state": "development"},
                    "relationships": {
                        "property": {"data": {"id": "PR1", "type": "properties"}},
                    },
                }
            }
        if path == "/properties/PR1":
            return {"data": {"id": "PR1", "attributes": {"name": "Web"}}}
        if path == "/libraries/LB_DEV/rules":
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
                        "relationships": {
                            "origin": {"data": {"id": "RL_NEW", "type": "rules"}},
                        },
                    },
                    {
                        "id": "RL_MOD_R3",
                        "attributes": {
                            "name": "Checkout",
                            "enabled": True,
                            "revision_number": 3,
                            "published": False,
                        },
                        "relationships": {
                            "origin": {"data": {"id": "RL_MOD", "type": "rules"}},
                        },
                    },
                    {
                        "id": "RL_OFF_R2",
                        "attributes": {
                            "name": "Legacy",
                            "enabled": False,
                            "revision_number": 2,
                            "published": False,
                        },
                        "relationships": {
                            "origin": {"data": {"id": "RL_OFF", "type": "rules"}},
                        },
                    },
                    {
                        "id": "RL_SAME_LIVE",
                        "attributes": {
                            "name": "Unchanged",
                            "enabled": True,
                            "revision_number": 1,
                            "published": True,
                        },
                        "relationships": {
                            "origin": {"data": {"id": "RL_SAME", "type": "rules"}},
                        },
                    },
                ]
            }
        if path in {
            "/libraries/LB_DEV/data_elements",
            "/libraries/LB_DEV/extensions",
        }:
            return {"data": []}
        if path == "/rules/RL_NEW":
            return {
                "data": {
                    "id": "RL_NEW",
                    "attributes": {
                        "name": "Brand New",
                        "enabled": True,
                        "revision_number": 0,
                        "published": False,
                    },
                    "meta": {"latest_revision_number": 1},
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
        if path == "/rules/RL_MOD":
            return {
                "data": {
                    "id": "RL_MOD",
                    "attributes": {
                        "name": "Checkout",
                        "enabled": True,
                        "revision_number": 0,
                        "published": False,
                    },
                    "meta": {"latest_revision_number": 3},
                }
            }
        if path == "/rules/RL_MOD/revisions":
            return {
                "data": [
                    {
                        "id": "RL_MOD_R2",
                        "attributes": {
                            "name": "Checkout",
                            "enabled": True,
                            "revision_number": 2,
                            "published": True,
                            "published_at": "2026-01-01T00:00:00.000Z",
                        },
                    },
                    {
                        "id": "RL_MOD_R3",
                        "attributes": {
                            "name": "Checkout",
                            "enabled": True,
                            "revision_number": 3,
                            "published": False,
                        },
                    },
                ]
            }
        if path == "/rules/RL_OFF":
            return {
                "data": {
                    "id": "RL_OFF",
                    "attributes": {
                        "name": "Legacy",
                        "enabled": False,
                        "revision_number": 0,
                        "published": False,
                    },
                    "meta": {"latest_revision_number": 2},
                }
            }
        if path == "/rules/RL_OFF/revisions":
            return {
                "data": [
                    {
                        "id": "RL_OFF_LIVE",
                        "attributes": {
                            "name": "Legacy",
                            "enabled": True,
                            "revision_number": 1,
                            "published": True,
                            "published_at": "2026-01-01T00:00:00.000Z",
                        },
                    },
                    {
                        "id": "RL_OFF_R2",
                        "attributes": {
                            "name": "Legacy",
                            "enabled": False,
                            "revision_number": 2,
                            "published": False,
                        },
                    },
                ]
            }
        if path == "/rules/RL_SAME":
            return {
                "data": {
                    "id": "RL_SAME",
                    "attributes": {
                        "name": "Unchanged",
                        "enabled": True,
                        "revision_number": 0,
                        "published": True,
                    },
                    "meta": {"latest_revision_number": 1},
                }
            }
        if path == "/rules/RL_SAME/revisions":
            return {
                "data": [
                    {
                        "id": "RL_SAME_LIVE",
                        "attributes": {
                            "name": "Unchanged",
                            "enabled": True,
                            "revision_number": 1,
                            "published": True,
                            "published_at": "2026-01-01T00:00:00.000Z",
                        },
                    }
                ]
            }
        raise AssertionError(f"Unexpected path: {path}")


@pytest.mark.asyncio
async def test_review_development_library_classifies_members() -> None:
    reactor = _DevReviewReactor()
    service = LibrariesService(
        reactor,  # type: ignore[arg-type]
        default_page_size=25,
        max_page_size=50,
        revision_service=RevisionService(reactor),  # type: ignore[arg-type]
    )
    view = await service.review_development_library("LB_DEV", depth="summary")

    assert view["resourceType"] == "developmentLibraryReview"
    assert view["depth"] == "summary"
    assert "idUsage" in view
    rules = {row["pending"]["id"]: row for row in view["changes"]["rules"]}
    assert set(rules) == {"RL_NEW_R1", "RL_MOD_R3", "RL_OFF_R2"}
    assert rules["RL_NEW_R1"]["changeKind"] == "new"
    assert "publishedLive" not in rules["RL_NEW_R1"]
    assert "headId" not in rules["RL_NEW_R1"]
    assert rules["RL_MOD_R3"]["changeKind"] == "modified"
    assert rules["RL_MOD_R3"]["publishedLive"]["id"] == "RL_MOD_R2"
    assert rules["RL_MOD_R3"]["pending"]["id"] == "RL_MOD_R3"
    assert rules["RL_OFF_R2"]["changeKind"] == "disabled"
    assert rules["RL_OFF_R2"]["publishedLive"]["enabled"] is True
    assert rules["RL_OFF_R2"]["pending"]["enabled"] is False
    assert view["summary"]["totalChanges"] == 3


class _PublishedLibraryReactor:
    async def get(self, path: str, params=None):
        if path == "/libraries/LB_PUB":
            return {
                "data": {
                    "id": "LB_PUB",
                    "type": "libraries",
                    "attributes": {
                        "name": "Already Published",
                        "state": "published",
                        "published_at": "2026-01-01T00:00:00.000Z",
                    },
                }
            }
        raise AssertionError(f"Unexpected path: {path}")


@pytest.mark.asyncio
async def test_review_development_library_rejects_non_development_state() -> None:
    from app.adobe.reactor_client import ReactorApiError

    reactor = _PublishedLibraryReactor()
    service = LibrariesService(
        reactor,  # type: ignore[arg-type]
        default_page_size=25,
        max_page_size=50,
        revision_service=RevisionService(reactor),  # type: ignore[arg-type]
    )
    with pytest.raises(ReactorApiError) as exc_info:
        await service.review_development_library("LB_PUB")
    assert exc_info.value.code == "NOT_A_DEVELOPMENT_LIBRARY"
    assert exc_info.value.status_code == 400
    assert "only for reviewing development libraries" in exc_info.value.message
    assert "published" in exc_info.value.message


def test_session_manager_workspace_roundtrip() -> None:
    path = Path(tempfile.gettempdir()) / "adobe-tags-session-test.json"
    if path.exists():
        path.unlink()
    store = SessionStore(path)
    manager = SessionManager(store)
    manager.update_workspace(
        active_property_id="PR1",
        active_property_name="Web",
        active_library_id="LB1",
        active_library_name="Dev",
    )
    session = manager.present_session()
    assert session["activePropertyId"] == "PR1"
    assert session["activeLibraryId"] == "LB1"
    manager.clear_workspace()
    assert manager.present_session()["activePropertyId"] is None
    if path.exists():
        path.unlink()
