from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from app.adobe.jsonapi import as_list, eq_filter, reactor_page_number, relationship_id
from app.adobe.list_pages import fetch_all_list_pages
from app.adobe.reactor_client import ReadOnlyReactorClient, ReactorApiError
from app.presenters.activity import (
    present_audit_event_row,
    present_deployment_row,
    present_property_activity,
)
from app.presenters.library import present_library_index

ActivityFocus = Literal["deployments", "edits", "all"]


class ActivityServiceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_window_bound(value: str, *, end_of_day: bool) -> datetime:
    """Parse ISO date or datetime into timezone-aware UTC datetime."""
    raw = value.strip()
    if not raw:
        raise ActivityServiceError("INVALID_WINDOW", "Window bound cannot be empty.")

    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        try:
            day = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ActivityServiceError(
                "INVALID_WINDOW", f"Invalid date '{value}'. Use YYYY-MM-DD or ISO-8601."
            ) from exc
        if end_of_day:
            return day + timedelta(days=1) - timedelta(microseconds=1)
        return day

    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ActivityServiceError(
            "INVALID_WINDOW", f"Invalid datetime '{value}'. Use YYYY-MM-DD or ISO-8601."
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def resolve_activity_window(
    *,
    from_value: str | None,
    to_value: str | None,
) -> tuple[datetime, datetime]:
    if not from_value and not to_value:
        raise ActivityServiceError(
            "INVALID_WINDOW",
            "Provide from and/or to (YYYY-MM-DD or ISO-8601) for the activity window.",
        )
    if from_value and not to_value:
        start = parse_window_bound(from_value, end_of_day=False)
        # Single bound "from" alone: treat as open-ended to now
        end = datetime.now(timezone.utc)
        return start, end
    if to_value and not from_value:
        end = parse_window_bound(to_value, end_of_day=True)
        # Open start — caller should still pass from for prior-deploy semantics;
        # default to a wide past so "prior" still works relative to end.
        start = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return start, end

    start = parse_window_bound(from_value or "", end_of_day=False)
    end = parse_window_bound(to_value or "", end_of_day=True)
    if end < start:
        raise ActivityServiceError("INVALID_WINDOW", "'to' must be on or after 'from'.")
    return start, end


def _parse_iso(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def select_deployments_for_window(
    published_libraries: list[dict[str, Any]],
    *,
    window_start: datetime,
    window_end: datetime,
    prior_limit: int = 3,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split published libs into in-window vs last N strictly before window_start.

    Libraries must already be newest-first by publishedAt.
    """
    dated: list[tuple[datetime, dict[str, Any]]] = []
    for library in published_libraries:
        published_at = _parse_iso(library.get("publishedAt"))
        if published_at is None:
            continue
        dated.append((published_at, library))

    in_window = [
        library
        for published_at, library in dated
        if window_start <= published_at <= window_end
    ]
    if in_window:
        return in_window, []

    prior = [
        library
        for published_at, library in dated
        if published_at < window_start
    ]
    return [], prior[: max(prior_limit, 0)]


def build_activity_narrative(
    *,
    window_label: str,
    deployments_in_window: list[dict[str, Any]],
    prior_deployments: list[dict[str, Any]],
    edits_in_window: list[dict[str, Any]],
    focus: ActivityFocus,
    edits_incomplete: bool = False,
) -> str:
    parts: list[str] = []

    if focus in {"deployments", "all"}:
        if deployments_in_window:
            parts.append(
                f"{len(deployments_in_window)} published deployment(s) found {window_label}."
            )
        elif prior_deployments:
            parts.append(
                f"No published deployments {window_label}. "
                f"Showing the last {len(prior_deployments)} deployment(s) before the window start."
            )
        else:
            parts.append(
                f"No published deployments {window_label}, and none were found before the window start."
            )

    if focus in {"edits", "all"}:
        if edits_in_window:
            parts.append(
                f"{len(edits_in_window)} resource edit event(s) (create/update/delete) {window_label}."
            )
        elif edits_incomplete:
            parts.append(
                f"No resource edit audit events for this property were found in the scanned "
                f"org-wide audit pages {window_label}; the audit scan hit its page limit so "
                f"edits may still exist."
            )
        else:
            parts.append(f"No resource edit audit events {window_label}.")
        if edits_incomplete and edits_in_window:
            parts.append("Audit scan hit its page limit; older edits in the window may be missing.")

    return " ".join(parts)


class ActivityService:
    def __init__(
        self,
        reactor: ReadOnlyReactorClient,
        *,
        max_library_pages: int = 10,
        max_audit_pages: int = 8,
        page_size: int = 50,
    ):
        self._reactor = reactor
        self._max_library_pages = max_library_pages
        self._max_audit_pages = max_audit_pages
        self._page_size = page_size

    async def _fetch_published_library_views(self, property_id: str) -> list[dict[str, Any]]:
        libraries = await fetch_all_list_pages(
            self._reactor,
            f"/properties/{property_id}/libraries",
            params={
                "filter[state]": eq_filter("published"),
                "sort": "-published_at",
            },
            page_size=self._page_size,
            max_pages=self._max_library_pages,
        )
        env_ids = {relationship_id(lib, "environment") for lib in libraries}
        env_ids.discard(None)
        env_lookup: dict[str, dict[str, Any]] = {}
        for env_id in env_ids:
            assert env_id is not None
            try:
                payload = await self._reactor.get(f"/environments/{env_id}")
                item = (payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}
                attributes = item.get("attributes") or {}
                env_lookup[env_id] = {
                    "id": item.get("id") or env_id,
                    "name": attributes.get("name"),
                    "stage": attributes.get("stage"),
                }
            except ReactorApiError:
                env_lookup[env_id] = {"id": env_id}

        views: list[dict[str, Any]] = []
        for library in libraries:
            env_id = relationship_id(library, "environment")
            views.append(
                present_library_index(
                    library,
                    environment=env_lookup.get(env_id) if env_id else None,
                )
            )
        return views

    async def _fetch_audit_pages(
        self,
        *,
        params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], bool]:
        """Fetch audit events; truncated=True when max_pages stopped with more pages left."""
        items: list[dict[str, Any]] = []
        page = 1
        for _ in range(self._max_audit_pages):
            request_params = {
                **params,
                "page[size]": self._page_size,
                "page[number]": reactor_page_number(page),
            }
            payload = await self._reactor.get("/audit_events", params=request_params)
            items.extend(as_list(payload))
            pagination = (payload.get("meta") or {}).get("pagination") or {}
            next_page = pagination.get("next_page")
            if next_page is None:
                return items, False
            next_page_int = int(next_page)
            if next_page_int <= page:
                return items, False
            page = next_page_int
        return items, True

    async def _fetch_audit_events_in_window(
        self,
        property_id: str,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Return (property-matched events, incomplete_scan)."""
        start_iso = window_start.isoformat().replace("+00:00", "Z")
        end_iso = window_end.isoformat().replace("+00:00", "Z")
        params: dict[str, Any] = {
            "filter[created_at]": f"BT {start_iso},{end_iso}",
            "sort": "-created_at",
        }
        truncated = False
        try:
            events, truncated = await self._fetch_audit_pages(params=params)
        except ReactorApiError:
            # Fallback without server-side date filter if Adobe rejects BT
            events, truncated = await self._fetch_audit_pages(
                params={"sort": "-created_at"}
            )
            truncated = True  # fallback cannot prove window completeness

        matched: list[dict[str, Any]] = []
        for event in events:
            prop_id = relationship_id(event, "property")
            if prop_id and prop_id != property_id:
                continue
            if not prop_id:
                continue
            created = _parse_iso((event.get("attributes") or {}).get("created_at"))
            if created is None or not (window_start <= created <= window_end):
                continue
            matched.append(event)
        return matched, truncated

    async def get_property_activity(
        self,
        property_id: str,
        *,
        from_value: str | None = None,
        to_value: str | None = None,
        focus: ActivityFocus = "all",
        prior_deploy_limit: int = 3,
    ) -> dict[str, Any]:
        window_start, window_end = resolve_activity_window(
            from_value=from_value, to_value=to_value
        )
        if prior_deploy_limit < 1 or prior_deploy_limit > 10:
            raise ActivityServiceError(
                "INVALID_PRIOR_LIMIT",
                "priorDeployLimit must be between 1 and 10.",
            )
        if focus not in {"deployments", "edits", "all"}:
            raise ActivityServiceError(
                "INVALID_FOCUS",
                "focus must be one of: deployments, edits, all.",
            )

        window = {
            "from": window_start.isoformat().replace("+00:00", "Z"),
            "to": window_end.isoformat().replace("+00:00", "Z"),
            "fromInput": from_value,
            "toInput": to_value,
        }
        window_label = f"between {window['from']} and {window['to']}"

        deployments_in_window: list[dict[str, Any]] = []
        prior_deployments: list[dict[str, Any]] = []
        edits_in_window: list[dict[str, Any]] = []

        if focus in {"deployments", "all"}:
            published = await self._fetch_published_library_views(property_id)
            in_window_libs, prior_libs = select_deployments_for_window(
                published,
                window_start=window_start,
                window_end=window_end,
                prior_limit=prior_deploy_limit,
            )
            deployments_in_window = [present_deployment_row(item) for item in in_window_libs]
            prior_deployments = [present_deployment_row(item) for item in prior_libs]

        edits_incomplete = False
        if focus in {"edits", "all"}:
            events, edits_incomplete = await self._fetch_audit_events_in_window(
                property_id,
                window_start=window_start,
                window_end=window_end,
            )
            edits_in_window = [present_audit_event_row(event) for event in events]

        narrative = build_activity_narrative(
            window_label=window_label,
            deployments_in_window=deployments_in_window,
            prior_deployments=prior_deployments,
            edits_in_window=edits_in_window,
            focus=focus,
            edits_incomplete=edits_incomplete,
        )

        return present_property_activity(
            property_id=property_id,
            window=window,
            focus=focus,
            deployments_in_window=deployments_in_window,
            prior_deployments=prior_deployments,
            edits_in_window=edits_in_window,
            narrative=narrative,
            edits_incomplete=edits_incomplete,
        )
