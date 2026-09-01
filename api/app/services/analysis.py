from __future__ import annotations

import json
from typing import Any, Literal

from app.adobe.jsonapi import relationship_id
from app.adobe.list_pages import fetch_all_list_pages
from app.adobe.reactor_client import ReadOnlyReactorClient, ReactorApiError
from app.adobe.revision_logic import revision_version
from app.presenters.analysis import present_rule_dependencies
from app.presenters.common import extract_data_element_reference_hits
from app.services.resource_helpers import fetch_resource_with_meta
from app.services.revisions import ResolvedVersions, RevisionService

VersionScope = Literal["latest", "live"]


class AnalysisService:
    def __init__(
        self,
        reactor: ReadOnlyReactorClient,
        max_scan_pages: int = 20,
        revision_service: RevisionService | None = None,
    ):
        self._reactor = reactor
        self._max_scan_pages = max_scan_pages
        self._revision_service = revision_service

    async def _fetch_property_resource_index(
        self,
        property_id: str,
        collection: str,
    ) -> list[dict[str, Any]]:
        return await fetch_all_list_pages(
            self._reactor,
            f"/properties/{property_id}/{collection}",
            page_size=50,
            max_pages=self._max_scan_pages,
        )

    async def _collect_rule_dependency_texts(
        self,
        scan_rule_id: str,
    ) -> tuple[list[str], set[str]]:
        components = await fetch_all_list_pages(
            self._reactor,
            f"/rules/{scan_rule_id}/rule_components",
            page_size=50,
            max_pages=self._max_scan_pages,
        )
        texts: list[str] = []
        extension_ids: set[str] = set()
        for component in components:
            attributes = component.get("attributes") or {}
            texts.extend(self._settings_scan_texts(attributes.get("settings")))
            extension_id = relationship_id(component, "extension")
            if extension_id:
                extension_ids.add(extension_id)
        return texts, extension_ids

    @staticmethod
    def _collect_string_leaves(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            leaves: list[str] = []
            for nested in value.values():
                leaves.extend(AnalysisService._collect_string_leaves(nested))
            return leaves
        if isinstance(value, list):
            leaves = []
            for nested in value:
                leaves.extend(AnalysisService._collect_string_leaves(nested))
            return leaves
        return []

    @classmethod
    def _settings_scan_texts(cls, settings: Any) -> list[str]:
        texts: list[str] = []
        if isinstance(settings, str):
            texts.append(settings)
            stripped = settings.strip()
            if stripped:
                try:
                    texts.extend(cls._collect_string_leaves(json.loads(stripped)))
                except json.JSONDecodeError:
                    pass
        elif settings is not None:
            texts.append(json.dumps(settings))
            texts.extend(cls._collect_string_leaves(settings))
        return texts

    def _build_version_context(
        self,
        *,
        version_scope: VersionScope,
        resolved: ResolvedVersions,
        scanned_item: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Minimal scanned-vs-live context — no publish timestamps or internal heuristics.

        publishState alone answers live/modified/neverPublished; published/publishedAt
        were removed because they read as if the scanned (often in-dev) revision is live.
        """
        live_item = resolved.live_item

        scanned_revision = None
        scanned_revision_id = None
        if scanned_item is not None:
            scanned_revision_id = scanned_item.get("id")
            if version_scope == "latest":
                scanned_revision = resolved.latest_version
            else:
                scanned_revision = revision_version(scanned_item)

        return {
            "scannedRevision": scanned_revision,
            "scannedRevisionId": scanned_revision_id,
            "liveRevision": revision_version(live_item) if live_item else None,
            "liveRevisionId": live_item.get("id") if live_item else None,
            "publishState": resolved.publish_state,
        }

    async def _resolve_data_elements(
        self,
        property_id: str,
        reference_hits: list[dict[str, str]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        data_element_items = await self._fetch_property_resource_index(property_id, "data_elements")
        de_by_name: dict[str, dict[str, Any]] = {}
        for item in data_element_items:
            de_attributes = item.get("attributes") or {}
            name = de_attributes.get("name")
            if isinstance(name, str) and name:
                de_by_name[name.casefold()] = item

        resolved_des: list[dict[str, Any]] = []
        unresolved: list[str] = []
        for hit in reference_hits:
            name = hit["name"]
            method = hit["detectionMethod"]
            item = de_by_name.get(name.casefold())
            if item:
                de_attributes = item.get("attributes") or {}
                resolved_des.append(
                    {
                        "id": item.get("id"),
                        "name": de_attributes.get("name"),
                        "enabled": de_attributes.get("enabled"),
                        "detectionMethod": method,
                    }
                )
            else:
                unresolved.append(name)
        return resolved_des, unresolved

    async def _resolve_extensions(self, extension_ids: set[str]) -> list[dict[str, Any]]:
        extensions: list[dict[str, Any]] = []
        for extension_id in sorted(extension_ids):
            try:
                ext_item, _ = await fetch_resource_with_meta(
                    self._reactor,
                    f"/extensions/{extension_id}",
                    not_found_message=f"Extension {extension_id} was not found.",
                )
                ext_attributes = ext_item.get("attributes") or {}
                extensions.append(
                    {
                        "id": ext_item.get("id"),
                        "name": ext_attributes.get("name") or ext_attributes.get("display_name"),
                        "enabled": ext_attributes.get("enabled"),
                        "installedExtensionVersion": ext_attributes.get("version"),
                    }
                )
            except ReactorApiError:
                extensions.append({"id": extension_id, "error": "unavailable"})
        return extensions

    async def get_rule_dependencies(
        self,
        rule_id: str,
        *,
        version_scope: VersionScope = "latest",
    ) -> dict[str, Any]:
        if version_scope not in {"latest", "live"}:
            raise ReactorApiError(
                "INVALID_VERSION_SCOPE",
                "versionScope must be 'latest' or 'live'.",
                400,
            )

        rule_item, _ = await fetch_resource_with_meta(
            self._reactor,
            f"/rules/{rule_id}",
            not_found_message=f"Rule {rule_id} was not found.",
        )
        property_id = relationship_id(rule_item, "property")
        if not property_id:
            raise ReactorApiError(
                "DEPENDENCY_SCAN_FAILED",
                f"Rule {rule_id} has no associated property.",
                422,
            )

        if self._revision_service is None:
            raise ReactorApiError(
                "REVISION_SERVICE_UNAVAILABLE",
                "Revision service is required for dependency analysis.",
                500,
            )

        resolved = await self._revision_service.resolve_versions(
            "rules",
            rule_id,
            head_item=rule_item,
        )
        attributes = rule_item.get("attributes") or {}
        rule_summary = {
            "id": rule_item.get("id"),
            "name": attributes.get("name"),
            "enabled": attributes.get("enabled"),
            "version": resolved.latest_version,
        }

        if version_scope == "live" and resolved.live_item is None:
            version_context = self._build_version_context(
                version_scope=version_scope,
                resolved=resolved,
                scanned_item=None,
            )
            return present_rule_dependencies(
                rule=rule_summary,
                data_elements=[],
                extensions=[],
                unresolved_data_element_names=[],
                version_scope=version_scope,
                version_context=version_context,
                live_dependencies_available=False,
            )

        if version_scope == "live":
            scanned_item = resolved.live_item
            assert scanned_item is not None
            scan_rule_id = str(scanned_item.get("id") or rule_id)
            # Align rule.id with the scanned revision so follow-up get_rule matches this graph.
            rule_summary["id"] = scan_rule_id
            rule_summary["version"] = revision_version(scanned_item) or resolved.latest_version
            rule_summary["enabled"] = (scanned_item.get("attributes") or {}).get("enabled")
        else:
            scanned_item = rule_item
            scan_rule_id = rule_id

        version_context = self._build_version_context(
            version_scope=version_scope,
            resolved=resolved,
            scanned_item=scanned_item,
        )

        texts, extension_ids = await self._collect_rule_dependency_texts(scan_rule_id)
        reference_hits = extract_data_element_reference_hits(*texts)
        resolved_des, unresolved = await self._resolve_data_elements(property_id, reference_hits)
        extensions = await self._resolve_extensions(extension_ids)

        return present_rule_dependencies(
            rule=rule_summary,
            data_elements=resolved_des,
            extensions=extensions,
            unresolved_data_element_names=unresolved,
            version_scope=version_scope,
            version_context=version_context,
            live_dependencies_available=True,
        )
