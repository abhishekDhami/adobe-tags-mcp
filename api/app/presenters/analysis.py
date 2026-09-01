from __future__ import annotations

from typing import Any


def present_rule_dependencies(
    *,
    rule: dict[str, Any],
    data_elements: list[dict[str, Any]],
    extensions: list[dict[str, Any]],
    unresolved_data_element_names: list[str],
    version_scope: str,
    version_context: dict[str, Any],
    live_dependencies_available: bool = True,
) -> dict[str, Any]:
    rule_name = rule.get("name") or rule.get("id") or "unknown"
    if version_scope == "live" and not live_dependencies_available:
        narrative = (
            f"Rule '{rule_name}' has never been published — "
            "no live dependency graph is available."
        )
    else:
        narrative_parts = []
        if data_elements:
            narrative_parts.append(f"{len(data_elements)} data element(s)")
        if extensions:
            narrative_parts.append(f"{len(extensions)} extension(s)")
        if unresolved_data_element_names:
            narrative_parts.append(f"{len(unresolved_data_element_names)} unresolved DE name(s)")
        narrative = (
            f"Rule '{rule_name}' references {', '.join(narrative_parts)}."
            if narrative_parts
            else f"Rule '{rule_name}' has no detected data element or extension dependencies."
        )

    view: dict[str, Any] = {
        "resourceType": "ruleDependencies",
        "versionScope": version_scope,
        "versionContext": version_context,
        "liveDependenciesAvailable": live_dependencies_available,
        "rule": {
            "id": rule.get("id"),
            "name": rule.get("name"),
            "enabled": rule.get("enabled"),
            "version": rule.get("version"),
        },
        "dataElements": data_elements,
        "extensions": extensions,
        "narrative": narrative,
    }
    if unresolved_data_element_names:
        view["unresolvedDataElementNames"] = unresolved_data_element_names
    return view
