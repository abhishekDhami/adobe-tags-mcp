from __future__ import annotations

from typing import Any


def present_usage_search(
    *,
    property_id: str,
    query: str,
    version_scope: str,
    status: str,
    mode: str = "freeText",
    detail: str = "hits",
    matched_data_element: dict[str, Any] | None = None,
    matches: list[dict[str, Any]] | None = None,
    hits: list[dict[str, Any]] | None = None,
    consumers: list[dict[str, Any]] | None = None,
    search_hits_raw: int = 0,
    search_hits_verified: int = 0,
    truncated: bool = False,
    notes: list[str] | None = None,
    library_id: str | None = None,
    auto_switched_to_free_text: bool = False,
) -> dict[str, Any]:
    scope_label = (
        "live (production) revisions"
        if version_scope == "live"
        else "latest saved (working) revisions"
    )

    if status == "needsDisambiguation":
        match_count = len(matches or [])
        narrative = (
            f"Query '{query}' matches {match_count} data element(s). "
            "Choose one id or exact name, then retry. No usage scan was run."
        )
    elif status == "notFound":
        narrative = (
            f"No data element named or identified by '{query}' was found on this property. "
            "No usage scan was run. For arbitrary settings text, retry with mode=freeText."
        )
    elif status == "ok":
        if detail == "hits":
            hit_rows = hits or []
            by_type: dict[str, int] = {}
            for row in hit_rows:
                key = str(row.get("resourceType") or "unknown")
                by_type[key] = by_type.get(key, 0) + 1
            parts = [f"{count} {kind}" for kind, count in sorted(by_type.items())]
            found = ", ".join(parts) if parts else "0 hit(s)"
            switched = (
                " No matching data element name was found, so free-text settings search was used."
                if auto_switched_to_free_text and mode == "freeText"
                else ""
            )
            narrative = (
                f"Based on {scope_label}.{switched} "
                f"High-level search for '{query}' found {found}. "
                "Use get_rule / get_data_element / get_extension on a hit id for details."
            )
        else:
            consumer_rows = consumers or []
            rule_count = sum(1 for row in consumer_rows if row.get("resourceType") == "rule")
            de_count = sum(
                1 for row in consumer_rows if row.get("resourceType") == "dataElement"
            )
            ext_count = sum(
                1 for row in consumer_rows if row.get("resourceType") == "extension"
            )
            parts = []
            if rule_count:
                parts.append(f"{rule_count} rule(s)")
            if de_count:
                parts.append(f"{de_count} data element(s)")
            if ext_count:
                parts.append(f"{ext_count} extension(s)")
            found = ", ".join(parts) if parts else "0 consumer(s)"

            if mode == "freeText":
                switched = (
                    " No matching data element name was found, so free-text settings search was used."
                    if auto_switched_to_free_text
                    else ""
                )
                narrative = (
                    f"Based on {scope_label}.{switched} "
                    f"Free-text search for '{query}' found {found}."
                )
            else:
                de_name = (matched_data_element or {}).get("name") or query
                narrative = (
                    f"Based on {scope_label}. "
                    f"Found {found} referencing data element '{de_name}'."
                )
        if library_id:
            narrative += f" Scoped to library {library_id}."
        if truncated:
            narrative += " Results may be incomplete (search/processing limits reached)."
    else:
        narrative = f"Based on {scope_label}."

    view: dict[str, Any] = {
        "resourceType": "usageSearch",
        "propertyId": property_id,
        "query": query,
        "mode": mode,
        "detail": detail,
        "versionScope": version_scope,
        "status": status,
        "method": "reactorSearch",
        "narrative": narrative,
        "idUsage": {
            "hits": (
                "Default detail=hits returns a simple list (id/name/type). "
                "Call get_rule / get_data_element / get_extension for one hit id when the user "
                "asks for more detail."
            ),
            "consumers": (
                "detail=summary|components returns enriched consumers. "
                "Use consumer id with get_rule / get_data_element / get_extension."
            ),
            "disambiguation": "When status=needsDisambiguation, pass a chosen data element id as query.",
            "scope": (
                "Default versionScope=latest (working copies). "
                "Pass versionScope=live when the user asks about production."
            ),
            "mode": (
                "mode=freeText (default) searches settings for the query string. "
                "Pass mode=dataElement for known DE name/id (token/getVar verify; "
                "auto-falls back to freeText if no DE matches). "
                "Search covers rule_components, data_elements, and extensions."
            ),
        },
    }
    if library_id:
        view["libraryId"] = library_id
    if auto_switched_to_free_text:
        view["autoSwitchedToFreeText"] = True
    if matched_data_element is not None:
        view["matchedDataElement"] = matched_data_element
    if matches is not None:
        view["matches"] = matches
    if hits is not None:
        view["hits"] = hits
        view["hitCount"] = len(hits)
    if consumers is not None:
        view["consumers"] = consumers
        view["consumerCount"] = len(consumers)
    if status == "ok":
        view["searchHitsRaw"] = search_hits_raw
        view["searchHitsVerified"] = search_hits_verified
        view["truncated"] = truncated
    if notes:
        view["notes"] = notes
    return view
