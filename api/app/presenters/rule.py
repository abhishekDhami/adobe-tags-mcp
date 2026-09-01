from __future__ import annotations

from typing import Any

from app.adobe.jsonapi import component_kind
from app.presenters.common import (
    audit_fields,
    code_field,
    parse_settings_field,
    revision_fields,
    view_meta,
)


from app.presenters.options import ViewOptions


def present_rule_index(item: dict[str, Any]) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    view: dict[str, Any] = {
        "resourceType": "rule",
        "id": item.get("id"),
        "name": attributes.get("name"),
        "enabled": attributes.get("enabled"),
    }
    return {k: v for k, v in view.items() if v is not None}


def _present_component(
    item: dict[str, Any],
    *,
    options: ViewOptions,
    extension_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    delegate = attributes.get("delegate_descriptor_id")
    extension_id = ((item.get("relationships") or {}).get("extension") or {}).get("data", {})
    ext_id = extension_id.get("id") if isinstance(extension_id, dict) else None

    component: dict[str, Any] = {
        "id": item.get("id"),
        "kind": component_kind(delegate if isinstance(delegate, str) else None),
        "name": attributes.get("name"),
        "delegateDescriptorId": delegate,
        "order": attributes.get("order"),
        "ruleOrder": attributes.get("rule_order"),
        "negate": attributes.get("negate"),
        "timeout": attributes.get("timeout"),
        "delayNext": attributes.get("delay_next"),
    }

    if ext_id:
        extension = extension_lookup.get(str(ext_id), {"id": str(ext_id)})
        component["extension"] = {
            "id": extension.get("id"),
            "name": extension.get("name"),
            "installedExtensionVersion": extension.get("installedExtensionVersion"),
        }
        if extension.get("error"):
            component["extension"]["error"] = extension["error"]

    include_full = options.include_full_content
    settings_block = parse_settings_field(
        attributes.get("settings"),
        include_raw=options.include_raw_settings,
        include_full=include_full,
        max_length=options.max_code_length,
    )
    component.update(settings_block)

    if options.include_full_content:
        component.update(code_field(attributes, include_full=True, max_length=0))

    return {k: v for k, v in component.items() if v is not None}


def present_rule(
    item: dict[str, Any],
    *,
    options: ViewOptions,
    components: list[dict[str, Any]] | None = None,
    extension_lookup: dict[str, dict[str, Any]] | None = None,
    property_summary: dict[str, Any] | None = None,
    version: int = 0,
) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    ext_lookup = extension_lookup or {}

    if options.depth == "index":
        return present_rule_index(item)

    view: dict[str, Any] = {
        "resourceType": "rule",
        "id": item.get("id"),
        "name": attributes.get("name"),
        "enabled": attributes.get("enabled"),
    }
    view.update(revision_fields(attributes))
    view.update(audit_fields(attributes))
    view["version"] = version

    if property_summary:
        view["property"] = property_summary

    truncated = False

    if options.include_logic and components is not None:
        presented = [
            _present_component(c, options=options, extension_lookup=ext_lookup) for c in components
        ]
        logic = {
            "events": [c for c in presented if c.get("kind") == "events"],
            "conditions": [c for c in presented if c.get("kind") == "conditions"],
            "actions": [c for c in presented if c.get("kind") == "actions"],
        }
        unknown = [c for c in presented if c.get("kind") == "unknown"]
        if unknown:
            logic["unknown"] = unknown
        view["logic"] = logic
        view["references"] = {
            "extensions": [
                {"id": eid, "name": ext_lookup[eid].get("name")}
                for eid in ext_lookup
                if ext_lookup[eid].get("name")
            ],
        }

    if options.depth in {"detail", "context", "full"} and options.include_full_content:
        code_block = code_field(
            attributes,
            include_full=True,
            max_length=0,
        )
        if code_block:
            view["code"] = code_block

    view["meta"] = view_meta(
        depth=options.depth,
        resource_type="rule",
        include_code=options.include_code,
        truncated=truncated,
    )
    return view
