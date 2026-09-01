from __future__ import annotations

import json
import re
from typing import Any

DATA_ELEMENT_REF_PATTERN = re.compile(
    r"%(data element|dataelement|de)\s*:\s*([^%]+)%",
    re.IGNORECASE,
)

# Static string literals only — dynamic getVar(variable) names are out of scope.
# Supports plain JS quotes and JSON-escaped quotes inside serialized settings.
SATELLITE_GETVAR_PATTERN = re.compile(
    r"""_satellite\s*\.\s*getVar\s*\(\s*(?:\\"([^"\\]*)\\"|\\'([^'\\]*)\\'|"([^"\\]*)"|'([^'\\]*)')\s*\)""",
    re.IGNORECASE,
)


def actor_from_attributes(attributes: dict[str, Any], prefix: str) -> dict[str, str] | None:
    email = attributes.get(f"{prefix}_by_email")
    display_name = attributes.get(f"{prefix}_by_display_name")
    if not email and not display_name:
        return None
    result: dict[str, str] = {}
    if email:
        result["email"] = str(email)
    if display_name:
        result["displayName"] = str(display_name)
    return result


def audit_fields(attributes: dict[str, Any]) -> dict[str, Any]:
    block: dict[str, Any] = {}
    created_at = attributes.get("created_at") or attributes.get("createdAt")
    updated_at = attributes.get("updated_at") or attributes.get("updatedAt")
    if created_at:
        block["createdAt"] = created_at
    if updated_at:
        block["updatedAt"] = updated_at
    created_by = actor_from_attributes(attributes, "created")
    updated_by = actor_from_attributes(attributes, "updated")
    if created_by:
        block["createdBy"] = created_by
    if updated_by:
        block["updatedBy"] = updated_by
    return block


def last_modified_block(attributes: dict[str, Any]) -> dict[str, Any] | None:
    block: dict[str, Any] = {}
    updated_at = attributes.get("updated_at") or attributes.get("updatedAt")
    if updated_at:
        block["at"] = updated_at
    updated_by = actor_from_attributes(attributes, "updated")
    if updated_by:
        block["by"] = updated_by
    return block or None


def revision_fields(attributes: dict[str, Any]) -> dict[str, Any]:
    block: dict[str, Any] = {}
    for src, dst in (
        ("published", "published"),
        ("published_at", "publishedAt"),
        ("review_status", "reviewStatus"),
    ):
        if src in attributes and attributes[src] is not None:
            block[dst] = attributes[src]
    return block


def relationship_id(item: dict[str, Any], relation: str) -> str | None:
    relationships = item.get("relationships") or {}
    relation_obj = relationships.get(relation) or {}
    data = relation_obj.get("data")
    if isinstance(data, dict):
        rel_id = data.get("id")
        return str(rel_id) if rel_id else None
    return None


def truncate_text(value: str, max_length: int, *, include_full: bool) -> dict[str, Any]:
    if include_full or max_length <= 0 or len(value) <= max_length:
        return {"value": value, "truncated": False}
    return {
        "preview": value[:max_length] + "…",
        "truncated": True,
        "hint": "Use depth=full and includeCode=true for the complete value.",
    }


def summarize_settings_value(value: Any) -> str:
    if isinstance(value, dict):
        parts = []
        for key, nested in list(value.items())[:8]:
            if isinstance(nested, (str, int, float, bool)) or nested is None:
                parts.append(f"{key}={nested}")
            else:
                parts.append(f"{key}=…")
        suffix = " …" if len(value) > 8 else ""
        return "{" + ", ".join(parts) + suffix + "}"
    if isinstance(value, list):
        return f"[{len(value)} items]"
    return str(value)


def parse_settings_field(
    raw_settings: Any,
    *,
    include_raw: bool,
    include_full: bool,
    max_length: int,
) -> dict[str, Any]:
    if raw_settings is None:
        return {}

    result: dict[str, Any] = {}
    if isinstance(raw_settings, str):
        if include_raw:
            result["settingsRaw"] = raw_settings if include_full else truncate_text(
                raw_settings, max_length, include_full=False
            )
        stripped = raw_settings.strip()
        if stripped:
            try:
                parsed = json.loads(stripped)
                result["settings"] = parsed
                result["settingsSummary"] = summarize_settings_value(parsed)
            except json.JSONDecodeError:
                text = truncate_text(raw_settings, max_length, include_full=include_full)
                result["settingsSummary"] = text.get("value") or text.get("preview")
                if text.get("truncated"):
                    result["settingsTruncated"] = True
        return result

    if isinstance(raw_settings, dict):
        result["settings"] = raw_settings
        result["settingsSummary"] = summarize_settings_value(raw_settings)
    return result


def code_field(
    attributes: dict[str, Any],
    *,
    include_full: bool,
    max_length: int,
) -> dict[str, Any]:
    block: dict[str, Any] = {}
    for key in ("custom_code", "default_value", "clean_text"):
        raw = attributes.get(key)
        if not isinstance(raw, str) or not raw:
            continue
        if include_full:
            block[key] = raw
        else:
            truncated = truncate_text(raw, max_length, include_full=False)
            if "preview" in truncated:
                block[f"{key}Preview"] = truncated["preview"]
                block[f"{key}Truncated"] = True
            else:
                block[key] = truncated["value"]
    return block


def extract_data_element_reference_hits(*texts: str | None) -> list[dict[str, str]]:
    """Extract DE name hits with detectionMethod: token | customCode.

    Token: ``%Data Element: Name%`` / ``%DE: Name%`` (and aliases).
    Custom code: ``_satellite.getVar("Name")`` / ``getVar('Name')`` string literals.
    When the same name is found by both methods, ``token`` wins.
    """
    hits: dict[str, dict[str, str]] = {}
    order: list[str] = []

    def _record(name: str, method: str) -> None:
        cleaned = name.strip()
        if not cleaned:
            return
        existing = hits.get(cleaned)
        if existing is None:
            hits[cleaned] = {"name": cleaned, "detectionMethod": method}
            order.append(cleaned)
            return
        if method == "token" and existing["detectionMethod"] != "token":
            existing["detectionMethod"] = "token"

    for text in texts:
        if not text:
            continue
        for match in DATA_ELEMENT_REF_PATTERN.finditer(text):
            _record(match.group(2), "token")
        for match in SATELLITE_GETVAR_PATTERN.finditer(text):
            name = next((group for group in match.groups() if group is not None), None)
            if name is not None:
                _record(name, "customCode")
    return [hits[name] for name in order]


def extract_data_element_references(*texts: str | None) -> list[str]:
    return [hit["name"] for hit in extract_data_element_reference_hits(*texts)]


def view_meta(
    *,
    depth: str,
    resource_type: str,
    include_code: bool,
    truncated: bool = False,
) -> dict[str, Any]:
    return {
        "depth": depth,
        "resourceType": resource_type,
        "codeIncluded": include_code,
        "truncated": truncated,
    }
