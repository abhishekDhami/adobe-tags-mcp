from __future__ import annotations

from typing import Any

from app.presenters.common import (
    audit_fields,
    parse_settings_field,
    revision_fields,
    relationship_id,
    view_meta,
)
from app.presenters.options import ViewOptions


def present_extension_index(item: dict[str, Any]) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    view: dict[str, Any] = {
        "resourceType": "extension",
        "id": item.get("id"),
        "name": attributes.get("name") or attributes.get("display_name"),
        "enabled": attributes.get("enabled"),
        "installedExtensionVersion": attributes.get("version"),
    }
    return {k: v for k, v in view.items() if v is not None}


def present_extension(
    item: dict[str, Any],
    *,
    options: ViewOptions,
    property_summary: dict[str, Any] | None = None,
    version: int = 0,
) -> dict[str, Any]:
    attributes = item.get("attributes") or {}

    if options.depth == "index":
        return present_extension_index(item)

    view: dict[str, Any] = {
        "resourceType": "extension",
        "id": item.get("id"),
        "name": attributes.get("name") or attributes.get("display_name"),
        "displayName": attributes.get("display_name"),
        "enabled": attributes.get("enabled"),
        "version": version,
        "installedExtensionVersion": attributes.get("version"),
        "delegateDescriptorId": attributes.get("delegate_descriptor_id"),
    }
    view.update(revision_fields(attributes))
    view.update(audit_fields(attributes))

    property_id = relationship_id(item, "property")
    if property_summary:
        view["property"] = property_summary
    elif property_id:
        view["property"] = {"id": property_id}

    include_full = options.include_full_content or options.depth == "full"
    view.update(
        parse_settings_field(
            attributes.get("settings"),
            include_raw=options.include_raw_settings,
            include_full=include_full,
            max_length=options.max_code_length,
        )
    )

    view["meta"] = view_meta(
        depth=options.depth,
        resource_type="extension",
        include_code=options.include_code,
    )
    return view


def extension_summary_from_item(item: dict[str, Any]) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    return {
        "id": item.get("id"),
        "name": attributes.get("name") or attributes.get("display_name"),
        "installedExtensionVersion": attributes.get("version"),
    }
