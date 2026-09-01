from __future__ import annotations

from typing import Any, Literal

from app.adobe.revision_logic import (
    derive_revision_published,
    latest_version_number,
    revision_is_live,
    revision_snapshot_summary,
)

RevisionView = Literal["important", "full"]

ROLE_IN_DEVELOPMENT_LIBRARY = "inDevelopmentLibrary"
ROLE_HEAD_NOT_IN_DEV_LIBRARY = "headNotInDevLibrary"
ROLE_PUBLISHED_OR_LIVE = "publishedOrLive"

ROLE_LEGEND = {
    ROLE_IN_DEVELOPMENT_LIBRARY: "Revision currently in a development library.",
    ROLE_HEAD_NOT_IN_DEV_LIBRARY: "Latest saved head, not in any development library.",
    ROLE_PUBLISHED_OR_LIVE: "Currently live and/or previously published (deployed).",
}


def classify_revision_roles(
    *,
    revision_id: str,
    head_id: str,
    is_live: bool,
    published: bool,
    development_library_revision_ids: set[str],
    include_in_development_library_role: bool = True,
    include_head_not_in_dev_library_role: bool = True,
) -> list[str]:
    """Return ordered importance roles for one revision snapshot."""
    roles: list[str] = []
    in_dev_lib = revision_id in development_library_revision_ids
    if include_in_development_library_role and in_dev_lib:
        roles.append(ROLE_IN_DEVELOPMENT_LIBRARY)
    if (
        include_head_not_in_dev_library_role
        and revision_id == head_id
        and not in_dev_lib
    ):
        roles.append(ROLE_HEAD_NOT_IN_DEV_LIBRARY)
    if is_live or published:
        roles.append(ROLE_PUBLISHED_OR_LIVE)
    return roles


def build_revision_candidates(
    *,
    head_item: dict[str, Any],
    revisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Union /revisions rows with head so head-not-in-lib is never dropped."""
    by_id: dict[str, dict[str, Any]] = {}
    for item in revisions:
        item_id = item.get("id")
        if item_id:
            by_id[str(item_id)] = item
    head_id = head_item.get("id")
    if head_id and str(head_id) not in by_id:
        by_id[str(head_id)] = head_item
    return list(by_id.values())


def annotate_and_filter_revisions(
    *,
    head_item: dict[str, Any],
    revisions: list[dict[str, Any]],
    live_item: dict[str, Any] | None,
    development_library_revision_ids: set[str],
    view: RevisionView = "important",
    include_in_development_library_role: bool = True,
    include_head_not_in_dev_library_role: bool = True,
) -> tuple[list[dict[str, Any]], int, int]:
    """Build newest-first annotated revision rows.

    Returns (visible_rows, important_count, full_revision_count).
    """
    head_id = str(head_item.get("id") or "")
    candidates = build_revision_candidates(head_item=head_item, revisions=revisions)
    latest_version = latest_version_number(head_item, revisions)

    annotated: list[dict[str, Any]] = []
    for item in candidates:
        item_id = str(item.get("id") or "")
        is_live = revision_is_live(item, live_item, head_item, revisions)
        published = derive_revision_published(item, is_live=is_live)
        roles = classify_revision_roles(
            revision_id=item_id,
            head_id=head_id,
            is_live=is_live,
            published=published,
            development_library_revision_ids=development_library_revision_ids,
            include_in_development_library_role=include_in_development_library_role,
            include_head_not_in_dev_library_role=include_head_not_in_dev_library_role,
        )
        # Head working copy often has revision_number=0; surface family latest instead.
        version_override = latest_version if item_id == head_id else None
        row = revision_snapshot_summary(
            item,
            version=version_override,
            is_live=is_live,
            published=published,
        )
        if roles:
            row["roles"] = roles
            row["important"] = True
        else:
            row["important"] = False
        annotated.append(row)

    # Newest first; head wins ties so pending work appears above same-numbered snapshots.
    annotated.sort(
        key=lambda row: (
            row.get("version") if row.get("version") is not None else -1,
            1 if row.get("id") == head_id else 0,
        ),
        reverse=True,
    )
    important_rows = [row for row in annotated if row.get("important")]
    visible = important_rows if view == "important" else annotated
    return visible, len(important_rows), len(annotated)


def present_important_revision_history(
    *,
    resource_kind: str,
    head_id: str,
    name: str | None,
    view: RevisionView,
    visible_revisions: list[dict[str, Any]],
    important_count: int,
    full_revision_count: int,
) -> dict[str, Any]:
    return {
        "resourceType": "revisionHistory",
        "resourceKind": resource_kind,
        "headId": head_id,
        "name": name,
        "view": view,
        "revisions": visible_revisions,
        "totalCount": len(visible_revisions),
        "importantCount": important_count,
        "fullRevisionCount": full_revision_count,
        "roleLegend": ROLE_LEGEND,
        "idUsage": {
            "important": "Default view=important returns only revisions with roles.",
            "full": "Pass view=full to include every revision; unimportant rows have important=false.",
            "followUp": "Use revision id with get_rule / get_data_element / get_extension.",
        },
    }
