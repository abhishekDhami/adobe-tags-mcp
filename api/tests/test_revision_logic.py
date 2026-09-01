from __future__ import annotations

from app.adobe.revision_logic import (
    derive_publish_state,
    derive_revision_published,
    latest_version_number,
    pick_live_revision,
    revision_is_live,
    revision_snapshot_summary,
    revision_version,
)
from app.presenters.revision import present_revision_history, present_version_summary


def _rule_head(revision_number: int = 0, **attrs) -> dict:
    meta_latest = attrs.pop("_meta_latest", revision_number)
    return {
        "id": "RL_HEAD",
        "type": "rules",
        "attributes": {
            "name": "Example Rule",
            "enabled": True,
            "revision_number": revision_number,
            "updated_at": "2026-01-02T00:00:00Z",
            "updated_by_email": "dev@example.com",
            "updated_by_display_name": "Dev User",
            **attrs,
        },
        "meta": {"latest_revision_number": meta_latest},
    }


def _revision(rev_id: str, revision_number: int, **attrs) -> dict:
    return {
        "id": rev_id,
        "type": "rules",
        "attributes": {
            "revision_number": revision_number,
            **attrs,
        },
    }


def test_revision_version_prefers_attribute() -> None:
    item = {"attributes": {"revision_number": 2}, "meta": {"latest_revision_number": 5}}
    assert revision_version(item) == 2


def test_latest_version_number_uses_head_meta() -> None:
    head = _rule_head(0, _meta_latest=3)
    revisions = [_revision("RL_R2", 2, published=True)]
    assert latest_version_number(head, revisions) == 3


def test_revision_snapshot_uses_head_with_version_override() -> None:
    head = _rule_head(0, _meta_latest=3)
    snapshot = revision_snapshot_summary(head, version=3)
    assert snapshot["version"] == 3
    assert snapshot["lastModified"]["by"]["email"] == "dev@example.com"
    assert "dirty" not in snapshot


def test_pick_live_revision_by_published_flag() -> None:
    head = _rule_head(0, _meta_latest=3)
    revisions = [
        _revision("RL_R1", 1, published=True, published_at="2026-01-01T00:00:00Z"),
        _revision("RL_R2", 2, published=False),
    ]
    live, method = pick_live_revision(head, revisions)
    assert live is not None
    assert live["id"] == "RL_R1"
    assert method == "published_flag"


def test_derive_publish_state_modified_when_head_ahead() -> None:
    head = _rule_head(0, _meta_latest=3)
    revisions = [
        _revision("RL_R1", 1, published=True),
        _revision("RL_R2", 2, published=False),
    ]
    live, _ = pick_live_revision(head, revisions)
    assert derive_publish_state(head, live, revisions) == "modified"


def test_derive_publish_state_live_when_versions_match() -> None:
    head = _rule_head(0, _meta_latest=2)
    revisions = [_revision("RL_R2", 2, published=True)]
    live, _ = pick_live_revision(head, revisions)
    assert derive_publish_state(head, live, revisions) == "live"


def test_present_version_summary_truncated_flag() -> None:
    view = present_version_summary(
        publish_state="modified",
        latest={"id": "RL_HEAD", "version": 3},
        live={"id": "RL1", "version": 2},
        live_resolution_method="published_flag",
        revisions_truncated=True,
    )
    assert view["revisionsTruncated"] is True


def test_present_revision_history() -> None:
    view = present_revision_history(
        resource_kind="rule",
        head_id="RL_HEAD",
        name="Example Rule",
        revisions=[
            {"id": "RL2", "version": 2, "isLive": False},
            {"id": "RL1", "version": 1, "isLive": True},
        ],
    )
    assert view["resourceType"] == "revisionHistory"
    assert view["totalCount"] == 2
    assert sum(1 for row in view["revisions"] if row.get("isLive")) == 1


def test_revision_is_live_matches_id() -> None:
    head = _rule_head(0, _meta_latest=2)
    live = _revision("RL_R2", 2, published=True)
    assert revision_is_live(live, live, head) is True
    assert revision_is_live(_revision("RL_R1", 1, published=True), live, head) is False


def test_revision_is_live_matches_version_when_live_is_head() -> None:
    head = _rule_head(0, _meta_latest=2)
    rev = _revision("RL_R2", 2, published=True)
    assert revision_is_live(rev, head, head, [rev]) is True


def test_derive_revision_published_user_semantics() -> None:
    v1 = _revision("R1", 1)
    v2 = _revision("R2", 2, published=True, published_at="2026-01-01T00:00:00Z")
    v3 = _revision("R3", 3)
    v4 = _revision("R4", 4)
    v5 = _revision("R5", 5, published=True, published_at="2026-02-01T00:00:00Z")

    assert derive_revision_published(v1, is_live=False) is False
    assert derive_revision_published(v2, is_live=False) is True
    assert derive_revision_published(v3, is_live=False) is False
    assert derive_revision_published(v4, is_live=False) is False
    assert derive_revision_published(v5, is_live=True) is True

    history = [
        revision_snapshot_summary(v5, is_live=True),
        revision_snapshot_summary(v4, is_live=False),
        revision_snapshot_summary(v3, is_live=False),
        revision_snapshot_summary(v2, is_live=False),
        revision_snapshot_summary(v1, is_live=False),
    ]
    assert [row["published"] for row in history] == [True, False, False, True, False]
    assert sum(1 for row in history if row["isLive"]) == 1


def test_latest_pending_revision_published_false_when_modified() -> None:
    head = _rule_head(0, _meta_latest=4, published=True)
    snapshot = revision_snapshot_summary(head, version=4, is_live=False, published=False)
    assert snapshot["published"] is False
    assert snapshot["isLive"] is False
