from __future__ import annotations

from typing import Any

from app.adobe.jsonapi import max_revision_number, parse_latest_revision_number, resource_meta
from app.presenters.common import last_modified_block


def revision_version(item: dict[str, Any]) -> int | None:
    attributes = item.get("attributes") or {}
    revision_number = attributes.get("revision_number")
    if isinstance(revision_number, int):
        return revision_number
    return parse_latest_revision_number(resource_meta(item))


def latest_version_number(head_item: dict[str, Any], revisions: list[dict[str, Any]]) -> int:
    numbers: list[int] = []
    from_meta = parse_latest_revision_number(resource_meta(head_item))
    if from_meta is not None:
        numbers.append(from_meta)
    head_attr_version = revision_version(head_item)
    if head_attr_version is not None:
        numbers.append(head_attr_version)
    from_revisions = max_revision_number(revisions)
    if from_revisions is not None:
        numbers.append(from_revisions)
    return max(numbers) if numbers else 0


def derive_revision_published(item: dict[str, Any], *, is_live: bool) -> bool:
    """True when this revision was deployed to production (live now or was live before)."""
    if is_live:
        return True
    attributes = item.get("attributes") or {}
    if attributes.get("published_at"):
        return True
    if attributes.get("published") is True:
        return True
    return False


def revision_snapshot_summary(
    item: dict[str, Any],
    *,
    version: int | None = None,
    is_live: bool = False,
    published: bool | None = None,
) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    resolved_published = (
        published if published is not None else derive_revision_published(item, is_live=is_live)
    )
    snapshot: dict[str, Any] = {
        "id": item.get("id"),
        "version": version if version is not None else revision_version(item),
        "published": resolved_published,
        "enabled": attributes.get("enabled"),
        "isLive": is_live,
    }
    if resolved_published:
        published_at = attributes.get("published_at")
        if published_at:
            snapshot["publishedAt"] = published_at
    review_status = attributes.get("review_status")
    if review_status is not None:
        snapshot["reviewStatus"] = review_status
    last_modified = last_modified_block(attributes)
    if last_modified:
        snapshot["lastModified"] = last_modified
    return {
        key: value
        for key, value in snapshot.items()
        if value is not None or key in {"published", "enabled"}
    }


def pick_live_revision(
    head_item: dict[str, Any],
    revisions: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    published_candidates = [
        item
        for item in revisions
        if (item.get("attributes") or {}).get("published") is True
    ]
    if published_candidates:
        live = max(
            published_candidates,
            key=lambda item: revision_version(item) if revision_version(item) is not None else -1,
        )
        return live, "published_flag"

    dated_candidates = [
        item
        for item in revisions
        if (item.get("attributes") or {}).get("published_at")
    ]
    if dated_candidates:
        live = max(
            dated_candidates,
            key=lambda item: str((item.get("attributes") or {}).get("published_at") or ""),
        )
        return live, "published_at"

    head_attributes = head_item.get("attributes") or {}
    if head_attributes.get("published") is True:
        published_or_dated = [
            item
            for item in revisions
            if (item.get("attributes") or {}).get("published") is True
            or (item.get("attributes") or {}).get("published_at")
        ]
        if published_or_dated:
            max_published_version = max(
                revision_version(item) if revision_version(item) is not None else -1
                for item in published_or_dated
            )
            head_version = latest_version_number(head_item, revisions)
            if head_version >= max_published_version:
                return head_item, "head_published_clean"
        else:
            return head_item, "head_published_clean"

    if head_attributes.get("published") is True and not revisions:
        return head_item, "head_published_clean"

    return None, "none"


def derive_publish_state(
    head_item: dict[str, Any],
    live_item: dict[str, Any] | None,
    revisions: list[dict[str, Any]],
) -> str:
    if live_item is None:
        return "neverPublished"

    pending_version = latest_version_number(head_item, revisions)
    live_version = revision_version(live_item)
    if live_version is not None and pending_version == live_version:
        return "live"
    if head_item.get("id") == live_item.get("id"):
        return "live"
    return "modified"


def revision_is_live(
    item: dict[str, Any],
    live_item: dict[str, Any] | None,
    head_item: dict[str, Any],
    revisions: list[dict[str, Any]] | None = None,
) -> bool:
    if live_item is None:
        return False
    if item.get("id") == live_item.get("id"):
        return True
    if live_item.get("id") == head_item.get("id"):
        live_version = revision_version(live_item)
        if live_version in (None, 0):
            live_version = latest_version_number(head_item, revisions or [])
        item_version = revision_version(item)
        return item_version is not None and item_version == live_version
    return False

