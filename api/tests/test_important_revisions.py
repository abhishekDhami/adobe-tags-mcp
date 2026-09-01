from __future__ import annotations

from app.adobe.important_revisions import (
    ROLE_HEAD_NOT_IN_DEV_LIBRARY,
    ROLE_IN_DEVELOPMENT_LIBRARY,
    ROLE_PUBLISHED_OR_LIVE,
    annotate_and_filter_revisions,
    classify_revision_roles,
)


def _head(*, version: int = 4) -> dict:
    return {
        "id": "RL_HEAD",
        "attributes": {
            "name": "Rule A",
            "revision_number": 0,
            "enabled": True,
            "updated_at": "2026-03-01T00:00:00Z",
        },
        "meta": {"latest_revision_number": version},
    }


def _rev(rev_id: str, version: int, **attrs) -> dict:
    return {
        "id": rev_id,
        "attributes": {"revision_number": version, "enabled": True, **attrs},
    }


def test_classify_roles_combinations() -> None:
    assert classify_revision_roles(
        revision_id="RL_DEV",
        head_id="RL_HEAD",
        is_live=False,
        published=False,
        development_library_revision_ids={"RL_DEV"},
    ) == [ROLE_IN_DEVELOPMENT_LIBRARY]

    assert classify_revision_roles(
        revision_id="RL_HEAD",
        head_id="RL_HEAD",
        is_live=False,
        published=False,
        development_library_revision_ids=set(),
    ) == [ROLE_HEAD_NOT_IN_DEV_LIBRARY]

    assert classify_revision_roles(
        revision_id="RL_HEAD",
        head_id="RL_HEAD",
        is_live=False,
        published=False,
        development_library_revision_ids={"RL_HEAD"},
    ) == [ROLE_IN_DEVELOPMENT_LIBRARY]

    assert classify_revision_roles(
        revision_id="RL_LIVE",
        head_id="RL_HEAD",
        is_live=True,
        published=True,
        development_library_revision_ids=set(),
    ) == [ROLE_PUBLISHED_OR_LIVE]


def test_important_view_filters_noise() -> None:
    head = _head(version=4)
    live = _rev("RL_V2", 2, published=True, published_at="2026-01-01T00:00:00Z")
    draft_in_lib = _rev("RL_V3", 3)
    noise = _rev("RL_V1", 1)
    # Head itself is candidate via build_revision_candidates

    visible, important_count, full_count = annotate_and_filter_revisions(
        head_item=head,
        revisions=[live, draft_in_lib, noise],
        live_item=live,
        development_library_revision_ids={"RL_V3"},
        view="important",
    )

    ids = [row["id"] for row in visible]
    assert ids == ["RL_HEAD", "RL_V3", "RL_V2"]
    assert important_count == 3
    assert full_count == 4  # head + 3 revisions
    by_id = {row["id"]: row for row in visible}
    assert by_id["RL_HEAD"]["roles"] == [ROLE_HEAD_NOT_IN_DEV_LIBRARY]
    assert by_id["RL_HEAD"]["version"] == 4
    assert by_id["RL_V3"]["roles"] == [ROLE_IN_DEVELOPMENT_LIBRARY]
    assert by_id["RL_V2"]["roles"] == [ROLE_PUBLISHED_OR_LIVE]
    assert by_id["RL_V2"]["isLive"] is True


def test_full_view_includes_unimportant() -> None:
    head = _head(version=3)
    live = _rev("RL_V2", 2, published=True, published_at="2026-01-01T00:00:00Z")
    noise = _rev("RL_V1", 1)

    visible, important_count, full_count = annotate_and_filter_revisions(
        head_item=head,
        revisions=[live, noise],
        live_item=live,
        development_library_revision_ids=set(),
        view="full",
    )

    assert full_count == 3
    assert important_count == 2  # head + live
    assert len(visible) == 3
    by_id = {row["id"]: row for row in visible}
    assert by_id["RL_V1"]["important"] is False
    assert "roles" not in by_id["RL_V1"]
    assert by_id["RL_HEAD"]["important"] is True
    assert by_id["RL_V2"]["important"] is True
