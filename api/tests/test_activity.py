from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.presenters.activity import present_audit_event_row, present_deployment_row
from app.services.activity import (
    ActivityServiceError,
    build_activity_narrative,
    parse_window_bound,
    resolve_activity_window,
    select_deployments_for_window,
)


def test_parse_date_only_end_of_day() -> None:
    start = parse_window_bound("2025-03-01", end_of_day=False)
    end = parse_window_bound("2025-03-31", end_of_day=True)
    assert start == datetime(2025, 3, 1, tzinfo=timezone.utc)
    assert end.day == 31
    assert end.hour == 23
    assert end.minute == 59


def test_resolve_window_requires_bounds() -> None:
    with pytest.raises(ActivityServiceError) as exc:
        resolve_activity_window(from_value=None, to_value=None)
    assert exc.value.code == "INVALID_WINDOW"


def test_select_deployments_in_window() -> None:
    libraries = [
        {"id": "LB3", "name": "May", "publishedAt": "2025-05-01T12:00:00Z"},
        {"id": "LB2", "name": "Mar late", "publishedAt": "2025-03-20T10:00:00Z"},
        {"id": "LB1", "name": "Mar early", "publishedAt": "2025-03-05T08:00:00Z"},
        {"id": "LB0", "name": "Feb", "publishedAt": "2025-02-01T08:00:00Z"},
    ]
    start = datetime(2025, 3, 1, tzinfo=timezone.utc)
    end = datetime(2025, 3, 31, 23, 59, 59, tzinfo=timezone.utc)
    in_window, prior = select_deployments_for_window(
        libraries, window_start=start, window_end=end, prior_limit=3
    )
    assert [item["id"] for item in in_window] == ["LB2", "LB1"]
    assert prior == []


def test_select_deployments_prior_to_window_not_latest_overall() -> None:
    """Ask March 2025 with no March deploys → last 3 before March, not Aug 2026."""
    libraries = [
        {"id": "LB_AUG", "name": "Aug 2026", "publishedAt": "2026-08-01T12:00:00Z"},
        {"id": "LB_JUL", "name": "Jul 2026", "publishedAt": "2026-07-01T12:00:00Z"},
        {"id": "LB_JUN", "name": "Jun 2025", "publishedAt": "2025-06-01T12:00:00Z"},
        {"id": "LB_FEB", "name": "Feb 2025", "publishedAt": "2025-02-15T12:00:00Z"},
        {"id": "LB_JAN", "name": "Jan 2025", "publishedAt": "2025-01-10T12:00:00Z"},
        {"id": "LB_DEC", "name": "Dec 2024", "publishedAt": "2024-12-01T12:00:00Z"},
        {"id": "LB_NOV", "name": "Nov 2024", "publishedAt": "2024-11-01T12:00:00Z"},
    ]
    start = datetime(2025, 3, 1, tzinfo=timezone.utc)
    end = datetime(2025, 3, 31, 23, 59, 59, tzinfo=timezone.utc)
    in_window, prior = select_deployments_for_window(
        libraries, window_start=start, window_end=end, prior_limit=3
    )
    assert in_window == []
    assert [item["id"] for item in prior] == ["LB_FEB", "LB_JAN", "LB_DEC"]
    assert "LB_AUG" not in {item["id"] for item in prior}


def test_narrative_prior_to_window() -> None:
    text = build_activity_narrative(
        window_label="between A and B",
        deployments_in_window=[],
        prior_deployments=[{"id": "1"}, {"id": "2"}, {"id": "3"}],
        edits_in_window=[],
        focus="all",
    )
    assert "No published deployments between A and B" in text
    assert "last 3 deployment(s) before the window start" in text
    assert "No resource edit audit events" in text


def test_narrative_edits_incomplete_does_not_claim_empty() -> None:
    text = build_activity_narrative(
        window_label="between A and B",
        deployments_in_window=[],
        prior_deployments=[],
        edits_in_window=[],
        focus="edits",
        edits_incomplete=True,
    )
    assert "page limit" in text
    assert "may still exist" in text


def test_present_audit_event_strips_entity_blob() -> None:
    row = present_audit_event_row(
        {
            "id": "AE1",
            "attributes": {
                "created_at": "2025-03-10T12:00:00.000Z",
                "type_of": "rule.updated",
                "display_name": "Page Load",
                "attributed_to_display_name": "Ada",
                "attributed_to_email": "ada@example.com",
                "entity": '{"data":{"attributes":{"name":"Page Load","enabled":true}}}',
            },
            "relationships": {
                "property": {"data": {"id": "PR1", "type": "properties"}},
                "entity": {"data": {"id": "RL1", "type": "rules"}},
            },
        }
    )
    assert row["action"] == "updated"
    assert row["resourceKind"] == "rule"
    assert row["resourceId"] == "RL1"
    assert row["who"]["email"] == "ada@example.com"
    assert "entity" not in row
    assert row["entityHint"]["name"] == "Page Load"


def test_present_deployment_row() -> None:
    row = present_deployment_row(
        {
            "id": "LB1",
            "name": "Fix",
            "publishedAt": "2025-03-10T00:00:00Z",
            "state": "published",
            "environment": {"id": "EN1", "stage": "production"},
        }
    )
    assert row["resourceType"] == "deployment"
    assert row["publishedAt"] == "2025-03-10T00:00:00Z"
