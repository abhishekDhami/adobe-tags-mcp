from __future__ import annotations

import json
from typing import Any


def present_deployment_row(library: dict[str, Any]) -> dict[str, Any]:
    """Curated published-library row for AI (no raw Adobe payload)."""
    row: dict[str, Any] = {
        "resourceType": "deployment",
        "id": library.get("id"),
        "name": library.get("name"),
        "publishedAt": library.get("publishedAt"),
        "state": library.get("state"),
    }
    environment = library.get("environment")
    if environment:
        row["environment"] = environment
    return {k: v for k, v in row.items() if v is not None}


_RESOURCE_KIND_ALIASES = {
    "data_element": "dataElement",
    "rule_component": "ruleComponent",
    "extension_package": "extensionPackage",
    "app_configuration": "appConfiguration",
}


def _normalize_resource_kind(raw: str) -> str:
    if raw in _RESOURCE_KIND_ALIASES:
        return _RESOURCE_KIND_ALIASES[raw]
    if "_" not in raw:
        return raw
    parts = raw.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


def present_audit_event_row(item: dict[str, Any]) -> dict[str, Any]:
    """Curated audit event — who / when / what, without dumping entity JSON."""
    attributes = item.get("attributes") or {}
    entity_ref = ((item.get("relationships") or {}).get("entity") or {}).get("data") or {}
    property_ref = ((item.get("relationships") or {}).get("property") or {}).get("data") or {}
    meta = item.get("meta") or {}

    type_of = attributes.get("type_of") or ""
    resource_kind_raw, _, action = type_of.partition(".")
    if not action:
        action = type_of or "unknown"
        resource_kind_raw = "unknown"
    resource_kind = _normalize_resource_kind(resource_kind_raw)

    row: dict[str, Any] = {
        "resourceType": "auditEvent",
        "id": item.get("id"),
        "at": attributes.get("created_at"),
        "action": action,
        "resourceKind": resource_kind,
        "resourceName": attributes.get("display_name"),
        "typeOf": type_of,
        "who": {
            "displayName": attributes.get("attributed_to_display_name"),
            "email": attributes.get("attributed_to_email"),
        },
    }
    if entity_ref.get("id"):
        row["resourceId"] = entity_ref.get("id")
        if entity_ref.get("type"):
            row["adobeResourceType"] = entity_ref.get("type")
    if property_ref.get("id"):
        row["propertyId"] = property_ref.get("id")
    property_name = meta.get("property_name")
    if property_name:
        row["propertyName"] = property_name

    # Optional one-line hint from entity snapshot (name/state only)
    hint = _entity_hint(attributes.get("entity"))
    if hint:
        row["entityHint"] = hint

    who = row["who"]
    row["who"] = {k: v for k, v in who.items() if v}
    if not row["who"]:
        del row["who"]
    return {k: v for k, v in row.items() if v is not None}


def _entity_hint(entity_raw: Any) -> dict[str, Any] | None:
    if not entity_raw or not isinstance(entity_raw, str):
        return None
    try:
        parsed = json.loads(entity_raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    data = parsed.get("data") if isinstance(parsed, dict) else None
    if not isinstance(data, dict):
        return None
    attributes = data.get("attributes") or {}
    hint: dict[str, Any] = {}
    if attributes.get("name"):
        hint["name"] = attributes["name"]
    if attributes.get("state"):
        hint["state"] = attributes["state"]
    if attributes.get("enabled") is not None:
        hint["enabled"] = attributes["enabled"]
    return hint or None


def present_property_activity(
    *,
    property_id: str,
    window: dict[str, Any],
    focus: str,
    deployments_in_window: list[dict[str, Any]],
    prior_deployments: list[dict[str, Any]],
    edits_in_window: list[dict[str, Any]],
    narrative: str,
    edits_incomplete: bool = False,
) -> dict[str, Any]:
    deployment_source = "inWindow" if deployments_in_window else "priorToWindow"
    edits: dict[str, Any] = {
        "inWindowCount": len(edits_in_window),
        "inWindow": edits_in_window,
    }
    if edits_incomplete:
        edits["incomplete"] = True
        edits["note"] = (
            "Audit events are org-wide; scan stopped at the page limit after client-side "
            "property filtering. Absence of rows does not prove there were no edits."
        )
    return {
        "resourceType": "propertyActivity",
        "propertyId": property_id,
        "window": window,
        "focus": focus,
        "deployments": {
            "source": deployment_source,
            "inWindowCount": len(deployments_in_window),
            "inWindow": deployments_in_window,
            "priorToWindow": prior_deployments if not deployments_in_window else [],
            "priorToWindowLimit": len(prior_deployments) if not deployments_in_window else 0,
        },
        "edits": edits,
        "narrative": narrative,
        "idUsage": {
            "deployments": "Use deployment.id with get_library / list_library_resources.",
            "edits": "Use resourceId with get_rule / get_data_element / get_extension / get_library as matching resourceKind.",
        },
    }
