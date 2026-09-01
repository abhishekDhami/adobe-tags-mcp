from __future__ import annotations

from typing import Any


def present_property_index(item: dict[str, Any]) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    view: dict[str, Any] = {
        "resourceType": "property",
        "id": item.get("id"),
        "name": attributes.get("name"),
        "platform": attributes.get("platform"),
        "enabled": attributes.get("enabled"),
    }
    return {k: v for k, v in view.items() if v is not None}


def present_search_index(item: dict[str, Any]) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    resource_type = item.get("type") or "resource"
    view: dict[str, Any] = {
        "resourceType": str(resource_type).replace("_", ""),
        "id": item.get("id"),
        "name": attributes.get("name"),
        "enabled": attributes.get("enabled"),
    }
    return {k: v for k, v in view.items() if v is not None}


def property_summary(item: dict[str, Any]) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    return {
        "id": item.get("id"),
        "name": attributes.get("name"),
    }
