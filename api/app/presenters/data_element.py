from __future__ import annotations

from typing import Any

from app.presenters.common import (
    audit_fields,
    code_field,
    parse_settings_field,
    revision_fields,
    relationship_id,
    view_meta,
)
from app.presenters.options import ViewOptions


def present_data_element_index(item: dict[str, Any]) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    view: dict[str, Any] = {
        "resourceType": "dataElement",
        "id": item.get("id"),
        "name": attributes.get("name"),
        "enabled": attributes.get("enabled"),
        "delegateDescriptorId": attributes.get("delegate_descriptor_id"),
    }
    return {k: v for k, v in view.items() if v is not None}


def present_data_element(
    item: dict[str, Any],
    *,
    options: ViewOptions,
    property_summary: dict[str, Any] | None = None,
    version: int = 0,
) -> dict[str, Any]:
    attributes = item.get("attributes") or {}

    if options.depth == "index":
        return present_data_element_index(item)

    view: dict[str, Any] = {
        "resourceType": "dataElement",
        "id": item.get("id"),
        "name": attributes.get("name"),
        "enabled": attributes.get("enabled"),
        "delegateDescriptorId": attributes.get("delegate_descriptor_id"),
    }
    view.update(revision_fields(attributes))
    view.update(audit_fields(attributes))
    view["version"] = version

    property_id = relationship_id(item, "property")
    if property_summary:
        view["property"] = property_summary
    elif property_id:
        view["property"] = {"id": property_id}

    include_full = options.include_full_content
    view.update(
        parse_settings_field(
            attributes.get("settings"),
            include_raw=options.include_raw_settings,
            include_full=include_full,
            max_length=options.max_code_length,
        )
    )
    view.update(code_field(attributes, include_full=include_full, max_length=options.max_code_length))

    if options.depth in {"context", "full"}:
        definition = attributes.get("default_value") or attributes.get("clean_text")
        if definition and "settingsSummary" not in view:
            view["definitionSummary"] = str(definition)[:200]

    truncated = any(
        view.get(flag) for flag in ("settingsTruncated", "custom_codeTruncated", "default_valueTruncated")
    )
    view["meta"] = view_meta(
        depth=options.depth,
        resource_type="dataElement",
        include_code=options.include_code,
        truncated=truncated,
    )
    return view
