from __future__ import annotations

from typing import Any


def clamp_page(page: int, page_size: int, default_size: int, max_size: int) -> tuple[int, int]:
    safe_page = max(page, 1)
    safe_size = min(max(page_size, 1), max_size) if page_size else default_size
    return safe_page, safe_size


def reactor_page_number(page: int) -> int:
    """Adobe Reactor list endpoints use 1-based page[number] (current_page starts at 1)."""
    return max(page, 1)


def paginate_meta(page: int, page_size: int, total_items: int) -> dict[str, int | bool]:
    if total_items <= 0:
        return {
            "page": page,
            "pageSize": page_size,
            "totalItems": 0,
            "totalPages": 0,
            "hasNextPage": False,
            "hasPreviousPage": False,
        }
    total_pages = max((total_items + page_size - 1) // page_size, 1)
    return {
        "page": page,
        "pageSize": page_size,
        "totalItems": total_items,
        "totalPages": total_pages,
        "hasNextPage": page < total_pages,
        "hasPreviousPage": page > 1,
    }


def as_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if data is None:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def resource_meta(item: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if payload:
        top = payload.get("meta")
        if isinstance(top, dict):
            merged.update(top)
    item_meta = item.get("meta")
    if isinstance(item_meta, dict):
        merged.update(item_meta)
    return merged


def parse_latest_revision_number(meta: dict[str, Any]) -> int | None:
    value = meta.get("latest_revision_number")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def max_revision_number(items: list[dict[str, Any]]) -> int | None:
    numbers: list[int] = []
    for item in items:
        meta_number = parse_latest_revision_number(resource_meta(item))
        if meta_number is not None:
            numbers.append(meta_number)
        attributes = item.get("attributes") or {}
        revision_number = attributes.get("revision_number")
        if isinstance(revision_number, int):
            numbers.append(revision_number)
    if not numbers:
        return None
    return max(numbers)


def eq_filter(value: str) -> str:
    """Reactor list filter operator form: filter[attr]=EQ value."""
    return f"EQ {value}"


def relationship_id(item: dict[str, Any], relation: str) -> str | None:
    relationships = item.get("relationships") or {}
    relation_obj = relationships.get(relation) or {}
    data = relation_obj.get("data")
    if isinstance(data, dict):
        rel_id = data.get("id")
        return str(rel_id) if rel_id else None
    return None


def summarize_resource(item: dict[str, Any], *, include_code: bool = False) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    summary: dict[str, Any] = {
        "id": item.get("id"),
        "type": item.get("type"),
        "name": attributes.get("name"),
        "enabled": attributes.get("enabled"),
        "createdAt": attributes.get("created_at") or attributes.get("createdAt"),
        "updatedAt": attributes.get("updated_at") or attributes.get("updatedAt"),
    }
    if include_code:
        for key in ("custom_code", "settings", "default_value", "clean_text"):
            if key in attributes:
                summary[key] = attributes[key]
    return {key: value for key, value in summary.items() if value is not None}


def summarize_rule(item: dict[str, Any], *, include_code: bool = False) -> dict[str, Any]:
    base = summarize_resource(item, include_code=include_code)
    attributes = item.get("attributes") or {}
    base["dirty"] = attributes.get("dirty")
    return base


def detail_resource(item: dict[str, Any], *, include_code: bool = True) -> dict[str, Any]:
    attributes = dict(item.get("attributes") or {})
    if not include_code:
        attributes.pop("custom_code", None)
        if isinstance(attributes.get("settings"), str) and len(attributes["settings"]) > 2000:
            attributes["settings"] = attributes["settings"][:2000] + "…"
    return {
        "id": item.get("id"),
        "type": item.get("type"),
        "attributes": attributes,
        "relationships": item.get("relationships"),
    }


def component_kind(delegate_descriptor_id: str | None) -> str:
    if not delegate_descriptor_id:
        return "unknown"
    parts = delegate_descriptor_id.split("::")
    if len(parts) >= 2 and parts[1] in {"events", "conditions", "actions"}:
        return parts[1]
    return "unknown"


def summarize_rule_component(item: dict[str, Any], *, include_settings: bool = True) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    delegate_descriptor_id = attributes.get("delegate_descriptor_id")
    summary: dict[str, Any] = {
        "id": item.get("id"),
        "type": item.get("type"),
        "kind": component_kind(delegate_descriptor_id if isinstance(delegate_descriptor_id, str) else None),
        "name": attributes.get("name"),
        "delegateDescriptorId": delegate_descriptor_id,
        "order": attributes.get("order"),
        "ruleOrder": attributes.get("rule_order"),
        "negate": attributes.get("negate"),
        "timeout": attributes.get("timeout"),
        "delayNext": attributes.get("delay_next"),
        "enabled": attributes.get("enabled"),
    }
    if include_settings and "settings" in attributes:
        settings = attributes["settings"]
        if isinstance(settings, str) and len(settings) > 2000:
            summary["settings"] = settings[:2000] + "…"
        else:
            summary["settings"] = settings
    extension_data = ((item.get("relationships") or {}).get("extension") or {}).get("data")
    if isinstance(extension_data, dict):
        summary["extensionId"] = extension_data.get("id")
    return {key: value for key, value in summary.items() if value is not None}
