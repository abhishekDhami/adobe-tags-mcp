from __future__ import annotations

from typing import Any


def present_version_summary(
    *,
    publish_state: str,
    latest: dict[str, Any],
    live: dict[str, Any] | None,
    live_resolution_method: str,
    revisions_truncated: bool = False,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "publishState": publish_state,
        "liveAvailable": live is not None,
        "latest": latest,
    }
    if live is not None:
        summary["live"] = live
    if live_resolution_method != "none":
        summary["liveResolutionMethod"] = live_resolution_method
    if revisions_truncated:
        summary["revisionsTruncated"] = True
    return summary


def present_revision_history(
    *,
    resource_kind: str,
    head_id: str,
    name: str | None,
    revisions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "resourceType": "revisionHistory",
        "resourceKind": resource_kind,
        "headId": head_id,
        "name": name,
        "revisions": revisions,
        "totalCount": len(revisions),
    }
