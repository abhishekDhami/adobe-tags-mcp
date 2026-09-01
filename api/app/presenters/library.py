from __future__ import annotations

from typing import Any, Literal

from app.adobe.jsonapi import relationship_id
from app.adobe.revision_logic import revision_version

LibraryResourceType = Literal["rule", "dataElement", "extension"]
ChangeKind = Literal["added", "modified", "unchanged"]
DevLibraryChangeKind = Literal["new", "modified", "disabled"]
DevLibraryReviewDepth = Literal["summary", "full"]


def _environment_ref(item: dict[str, Any]) -> dict[str, Any] | None:
    env_data = ((item.get("relationships") or {}).get("environment") or {}).get("data")
    if isinstance(env_data, dict) and env_data.get("id"):
        return {"id": env_data.get("id")}
    return None


def _library_timestamp(attributes: dict[str, Any]) -> dict[str, Any]:
    state = attributes.get("state")
    if state == "published":
        published_at = attributes.get("published_at")
        return {"publishedAt": published_at} if published_at else {}
    updated_at = attributes.get("updated_at")
    return {"updatedAt": updated_at} if updated_at else {}


def present_environment_index(item: dict[str, Any]) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    view: dict[str, Any] = {
        "resourceType": "environment",
        "id": item.get("id"),
        "name": attributes.get("name"),
        "stage": attributes.get("stage"),
        "path": attributes.get("path"),
    }
    return {k: v for k, v in view.items() if v is not None}


def present_library_index(
    item: dict[str, Any],
    *,
    environment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    view: dict[str, Any] = {
        "resourceType": "library",
        "id": item.get("id"),
        "name": attributes.get("name"),
        "state": attributes.get("state"),
        "buildRequired": attributes.get("build_required"),
    }
    view.update(_library_timestamp(attributes))
    if environment:
        view["environment"] = environment
    elif _environment_ref(item):
        view["environment"] = _environment_ref(item)
    return {k: v for k, v in view.items() if v is not None}


def present_library_detail(
    item: dict[str, Any],
    *,
    environment: dict[str, Any] | None = None,
    property_summary: dict[str, Any] | None = None,
    item_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    meta = item_meta or {}
    view: dict[str, Any] = {
        "resourceType": "library",
        "id": item.get("id"),
        "name": attributes.get("name"),
        "state": attributes.get("state"),
        "buildRequired": attributes.get("build_required"),
        "createdAt": attributes.get("created_at"),
        "updatedAt": attributes.get("updated_at"),
        "publishedAt": attributes.get("published_at"),
    }
    if environment:
        view["environment"] = environment
    property_id = relationship_id(item, "property")
    if property_summary:
        view["property"] = property_summary
    elif property_id:
        view["property"] = {"id": property_id}
    upstream = relationship_id(item, "upstream_library")
    if upstream:
        view["upstreamLibraryId"] = upstream
    build_status = meta.get("build_status")
    if build_status is not None:
        view["buildStatus"] = build_status
    build_detail = meta.get("build_required_detail")
    if build_detail:
        view["buildRequiredDetail"] = build_detail
    return {k: v for k, v in view.items() if v is not None}


def _change_kind(
    *,
    dirty: bool | None,
    published: bool | None,
    version: int,
    revision_number: int | None,
) -> ChangeKind:
    effective_revision = revision_number if isinstance(revision_number, int) else version
    if effective_revision == 0 and published is not True:
        return "added"
    if dirty:
        return "modified"
    if published is not True:
        return "modified"
    return "unchanged"


def present_library_resource_row(
    item: dict[str, Any],
    *,
    resource_type: LibraryResourceType,
    version: int,
) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    dirty = attributes.get("dirty")
    published = attributes.get("published")
    revision_number = attributes.get("revision_number")
    view: dict[str, Any] = {
        "resourceType": resource_type,
        "id": item.get("id"),
        "name": attributes.get("name"),
        "enabled": attributes.get("enabled"),
        "version": version,
        "dirty": dirty,
        "published": published,
        "publishedAt": attributes.get("published_at"),
        "updatedAt": attributes.get("updated_at"),
        "changeKind": _change_kind(
            dirty=dirty,
            published=published,
            version=version,
            revision_number=revision_number if isinstance(revision_number, int) else None,
        ),
    }
    return {k: v for k, v in view.items() if v is not None}


def classify_dev_library_change(
    *,
    live_item: dict[str, Any] | None,
    pending_item: dict[str, Any],
) -> DevLibraryChangeKind | None:
    """Classify a library member vs production.

    Returns None when the library holds the exact live revision (nothing to review).
    """
    if live_item is None:
        return "new"

    live_attrs = live_item.get("attributes") or {}
    pending_attrs = pending_item.get("attributes") or {}
    if live_attrs.get("enabled") is True and pending_attrs.get("enabled") is False:
        return "disabled"

    if live_item.get("id") == pending_item.get("id"):
        return None

    return "modified"


def present_dev_library_side(
    item: dict[str, Any],
    *,
    version: int | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lean side snapshot; optional richer ``detail`` for depth=full."""
    attributes = item.get("attributes") or {}
    side: dict[str, Any] = {
        "id": item.get("id"),
        "version": version if version is not None else revision_version(item),
        "enabled": attributes.get("enabled"),
    }
    if detail is not None:
        side["detail"] = detail
    return {k: v for k, v in side.items() if v is not None or k == "enabled"}


def present_dev_library_change_row(
    *,
    change_kind: DevLibraryChangeKind,
    resource_kind: LibraryResourceType,
    name: str | None,
    pending: dict[str, Any],
    published_live: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "changeKind": change_kind,
        "resourceKind": resource_kind,
        "name": name,
        "pending": pending,
    }
    if published_live is not None:
        row["publishedLive"] = published_live
    return {k: v for k, v in row.items() if v is not None}


def present_development_library_review(
    *,
    library: dict[str, Any],
    depth: DevLibraryReviewDepth,
    changes: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    rules = changes.get("rules") or []
    data_elements = changes.get("dataElements") or []
    extensions = changes.get("extensions") or []
    all_rows = rules + data_elements + extensions

    by_kind = {"new": 0, "modified": 0, "disabled": 0}
    for row in all_rows:
        kind = row.get("changeKind")
        if kind in by_kind:
            by_kind[kind] += 1

    narrative_parts = []
    if by_kind["new"]:
        narrative_parts.append(f"{by_kind['new']} new")
    if by_kind["modified"]:
        narrative_parts.append(f"{by_kind['modified']} modified")
    if by_kind["disabled"]:
        narrative_parts.append(f"{by_kind['disabled']} disabled")
    narrative = (
        f"Development library review ({depth}): {', '.join(narrative_parts)} "
        f"across {len(all_rows)} resource(s). "
        "Compare pending vs publishedLive. "
        "For follow-up get_*: use pending.id for the library revision, "
        "publishedLive.id for production (omit for new)."
        if narrative_parts
        else "Development library has no new, modified, or disabled resources to review."
    )

    return {
        "resourceType": "developmentLibraryReview",
        "depth": depth,
        "library": library,
        "summary": {
            "totalChanges": len(all_rows),
            "new": by_kind["new"],
            "modified": by_kind["modified"],
            "disabled": by_kind["disabled"],
            "rules": len(rules),
            "dataElements": len(data_elements),
            "extensions": len(extensions),
        },
        "idUsage": {
            "pending": "Revision added to this development library — use pending.id for get_rule / get_data_element / get_extension when inspecting what will publish.",
            "publishedLive": "Current production revision — use publishedLive.id to inspect what is live. Absent when changeKind is new.",
        },
        "changes": {
            "rules": rules,
            "dataElements": data_elements,
            "extensions": extensions,
        },
        "narrative": narrative,
    }


def present_ambiguous_libraries(
    *,
    message: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "ambiguous",
        "message": message,
        "candidates": candidates,
    }

