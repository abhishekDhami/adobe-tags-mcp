from __future__ import annotations

import asyncio
from typing import Any, Literal

from app.adobe.jsonapi import as_list
from app.adobe.list_pages import fetch_all_list_pages
from app.adobe.reactor_client import ReadOnlyReactorClient, ReactorApiError
from app.presenters.common import extract_data_element_reference_hits
from app.presenters.usage import present_usage_search
from app.services.revisions import RevisionService

VersionScope = Literal["latest", "live"]
UsageMode = Literal["dataElement", "freeText"]
UsageDetail = Literal["hits", "summary", "components"]

_SEARCH_PAGE_SIZE = 100
_MAX_SEARCH_PAGES = 2  # keep property-wide usage fast; truncated when more exist
_MAX_HITS_TO_PROCESS = 60
_MAX_FAMILIES = 25
_CONCURRENCY = 8
_COMBINED_RESOURCE_TYPES = ["rule_components", "data_elements", "extensions"]


class UsageServiceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class UsageService:
    """Property-wide reverse usage via Reactor /search (not full rule scans)."""

    def __init__(
        self,
        reactor: ReadOnlyReactorClient,
        *,
        revision_service: RevisionService | None = None,
        max_search_pages: int = _MAX_SEARCH_PAGES,
        max_hits_to_process: int = _MAX_HITS_TO_PROCESS,
        max_families: int = _MAX_FAMILIES,
        concurrency: int = _CONCURRENCY,
    ):
        self._reactor = reactor
        self._revision_service = revision_service
        self._max_search_pages = max_search_pages
        self._max_hits_to_process = max_hits_to_process
        self._max_families = max_families
        self._concurrency = concurrency

    async def find_usage(
        self,
        property_id: str,
        *,
        query: str,
        version_scope: VersionScope = "latest",
        mode: UsageMode = "freeText",
        detail: UsageDetail = "hits",
        library_id: str | None = None,
    ) -> dict[str, Any]:
        query = (query or "").strip()
        if not query:
            raise UsageServiceError("INVALID_QUERY", "query is required.")
        if version_scope not in {"latest", "live"}:
            raise UsageServiceError(
                "INVALID_VERSION_SCOPE",
                "versionScope must be 'latest' or 'live'.",
            )
        if mode not in {"dataElement", "freeText"}:
            raise UsageServiceError(
                "INVALID_MODE",
                "mode must be 'dataElement' or 'freeText'.",
            )
        if detail not in {"hits", "summary", "components"}:
            raise UsageServiceError(
                "INVALID_DETAIL",
                "detail must be 'hits', 'summary', or 'components'.",
            )

        matched: dict[str, Any] | None = None
        target_name: str | None = None
        effective_mode: UsageMode = mode
        auto_switched_to_free_text = False

        if mode == "dataElement":
            data_elements = await fetch_all_list_pages(
                self._reactor,
                f"/properties/{property_id}/data_elements",
                page_size=50,
                max_pages=10,
            )
            resolved = self._resolve_data_element_query(query, data_elements)
            if resolved["status"] == "needsDisambiguation":
                return present_usage_search(
                    property_id=property_id,
                    query=query,
                    version_scope=version_scope,
                    status="needsDisambiguation",
                    mode=mode,
                    detail=detail,
                    matches=resolved["matches"],
                    library_id=library_id,
                )
            if resolved["status"] == "notFound":
                effective_mode = "freeText"
                auto_switched_to_free_text = True
                settings_query = query
            else:
                matched = resolved["matched"]
                target_name = str(matched["name"])
                settings_query = target_name
        else:
            settings_query = query

        raw_hits, truncated = await self._search_settings_combined(
            property_id=property_id,
            settings_query=settings_query,
            version_scope=version_scope,
        )

        verified: list[dict[str, Any]] = []
        for hit in raw_hits:
            detection = self._verify_hit(
                hit,
                mode=effective_mode,
                target_name=target_name,
                free_text=query if effective_mode == "freeText" else None,
            )
            if not detection:
                continue
            if matched and hit.get("type") == "data_elements":
                hit_id = str(hit.get("id") or "")
                matched_id = str(matched.get("id") or "")
                if hit_id == matched_id or self._canonical_origin_id(hit) == matched_id:
                    continue
            verified.append({**hit, "_detectionMethod": detection})
            if len(verified) >= self._max_hits_to_process:
                truncated = True
                break

        notes = [
            "Property-scoped Adobe Reactor POST /search (one combined call) on "
            "rule_components + data_elements + extensions settings.",
            "Strict revision filters: latest → revision_number=0; live → published=true "
            "(falls back without filters if Adobe rejects the query shape).",
            "Default detail=hits is UI-like (high-level list only). "
            "Use get_rule / get_data_element / get_extension for one id, "
            "or detail=summary|components for enriched consumer aggregation.",
        ]
        if auto_switched_to_free_text:
            notes.append(
                "No data element matched the query; automatically used mode=freeText settings search."
            )
        if version_scope == "live":
            notes.append("Based on live (production) revision filter.")
        else:
            notes.append("Based on latest saved (working) revision filter.")

        # Fast path: no parent-rule / revisions fan-out.
        if detail == "hits":
            hits = [self._present_hit_row(hit) for hit in verified]
            return present_usage_search(
                property_id=property_id,
                query=query,
                version_scope=version_scope,
                status="ok",
                mode=effective_mode,
                detail=detail,
                matched_data_element=matched,
                hits=hits,
                search_hits_raw=len(raw_hits),
                search_hits_verified=len(verified),
                truncated=truncated,
                notes=notes,
                library_id=library_id,
                auto_switched_to_free_text=auto_switched_to_free_text,
            )

        library_member_ids: set[str] | None = None
        if library_id:
            library_member_ids = await self._library_member_ids(library_id)
            notes.append(
                f"Results limited to resources belonging to library {library_id}."
            )

        consumers = await self._build_consumers(
            verified_hits=verified,
            version_scope=version_scope,
            detail=detail,
            mode=effective_mode,
            target_name=target_name,
            free_text=query if effective_mode == "freeText" else None,
            exclude_data_element_id=str(matched["id"]) if matched else None,
            library_member_ids=library_member_ids,
        )
        notes.append(
            "detail=summary|components enriches hits into rule/DE/extension consumers "
            "(extra Adobe GETs)."
        )

        return present_usage_search(
            property_id=property_id,
            query=query,
            version_scope=version_scope,
            status="ok",
            mode=effective_mode,
            detail=detail,
            matched_data_element=matched,
            consumers=consumers,
            search_hits_raw=len(raw_hits),
            search_hits_verified=len(verified),
            truncated=truncated,
            notes=notes,
            library_id=library_id,
            auto_switched_to_free_text=auto_switched_to_free_text,
        )

    def _present_hit_row(self, hit: dict[str, Any]) -> dict[str, Any]:
        attributes = hit.get("attributes") or {}
        adobe_type = str(hit.get("type") or "")
        resource_type = {
            "rule_components": "ruleComponent",
            "data_elements": "dataElement",
            "extensions": "extension",
        }.get(adobe_type, adobe_type or "unknown")
        name = attributes.get("display_name") or attributes.get("name")
        row: dict[str, Any] = {
            "resourceType": resource_type,
            "id": hit.get("id"),
            "name": name,
            "detectionMethod": hit.get("_detectionMethod"),
            "revisionNumber": attributes.get("revision_number"),
            "published": attributes.get("published"),
        }
        origin_id = self._canonical_origin_id(hit)
        if origin_id and origin_id != str(hit.get("id") or ""):
            row["originId"] = origin_id
        delegate = attributes.get("delegate_descriptor_id")
        if delegate:
            row["delegateDescriptorId"] = delegate
        # Drop nulls for a cleaner AI payload.
        return {key: value for key, value in row.items() if value is not None}

    async def _search_settings_combined(
        self,
        *,
        property_id: str,
        settings_query: str,
        version_scope: VersionScope,
    ) -> tuple[list[dict[str, Any]], bool]:
        """One Adobe search across rule_components + data_elements + extensions."""
        return await self._search_settings(
            property_id=property_id,
            settings_query=settings_query,
            resource_types=_COMBINED_RESOURCE_TYPES,
            version_scope=version_scope,
        )

    async def _library_member_ids(self, library_id: str) -> set[str]:
        member_ids: set[str] = set()
        for collection in ("rules", "data_elements", "extensions"):
            try:
                items = await fetch_all_list_pages(
                    self._reactor,
                    f"/libraries/{library_id}/{collection}",
                    page_size=50,
                    max_pages=10,
                )
            except ReactorApiError:
                continue
            for item in items:
                item_id = item.get("id")
                if item_id:
                    member_ids.add(str(item_id))
                origin = self._canonical_origin_id(item)
                if origin:
                    member_ids.add(origin)
        return member_ids

    @staticmethod
    def _de_summary(item: dict[str, Any]) -> dict[str, Any]:
        attributes = item.get("attributes") or {}
        return {
            "id": item.get("id"),
            "name": attributes.get("name"),
            "enabled": attributes.get("enabled"),
        }

    @staticmethod
    def _canonical_origin_id(item: dict[str, Any]) -> str | None:
        relationships = item.get("relationships") or {}
        origin = relationships.get("origin") or {}
        data = origin.get("data")
        if isinstance(data, dict) and data.get("id"):
            return str(data["id"])
        item_id = item.get("id")
        return str(item_id) if item_id else None

    def _resolve_data_element_query(
        self,
        query: str,
        data_elements: list[dict[str, Any]],
    ) -> dict[str, Any]:
        by_id = [item for item in data_elements if str(item.get("id") or "") == query]
        if by_id:
            return {"status": "ok", "matched": self._de_summary(by_id[0])}

        query_fold = query.casefold()
        by_name = [
            item
            for item in data_elements
            if str((item.get("attributes") or {}).get("name") or "").casefold() == query_fold
        ]
        if len(by_name) == 1:
            return {"status": "ok", "matched": self._de_summary(by_name[0])}
        if len(by_name) > 1:
            return {
                "status": "needsDisambiguation",
                "matches": [self._de_summary(item) for item in by_name],
            }
        return {"status": "notFound"}

    async def _search_settings(
        self,
        *,
        property_id: str,
        settings_query: str,
        resource_types: list[str],
        version_scope: VersionScope,
    ) -> tuple[list[dict[str, Any]], bool]:
        items: list[dict[str, Any]] = []
        truncated = False
        for page_index in range(self._max_search_pages):
            query_fields: dict[str, Any] = {
                "attributes.settings": {"value": settings_query},
                "relationships.property.data.id": {"value": property_id},
            }
            # Narrow Adobe index to fewer historical revisions when possible.
            if version_scope == "live":
                query_fields["attributes.published"] = {"value": True}
            elif version_scope == "latest":
                query_fields["attributes.revision_number"] = {"value": 0}

            body = {
                "from": page_index * _SEARCH_PAGE_SIZE,
                "size": _SEARCH_PAGE_SIZE,
                "query": query_fields,
                "resource_types": resource_types,
            }
            try:
                payload = await self._reactor.search(body)
            except ReactorApiError:
                # Retry without scope filters if Adobe rejects boolean/int query shape.
                if "attributes.published" in query_fields or "attributes.revision_number" in query_fields:
                    body["query"] = {
                        "attributes.settings": {"value": settings_query},
                        "relationships.property.data.id": {"value": property_id},
                    }
                    payload = await self._reactor.search(body)
                else:
                    raise
            page_items = as_list(payload)
            items.extend(page_items)
            meta = payload.get("meta") or {}
            total_hits = meta.get("total_hits")
            if total_hits is None:
                total_hits = meta.get("total_count")
            if len(page_items) < _SEARCH_PAGE_SIZE:
                break
            if isinstance(total_hits, int) and len(items) >= total_hits:
                break
            if page_index == self._max_search_pages - 1:
                truncated = True
        return items, truncated

    def _verify_hit(
        self,
        item: dict[str, Any],
        *,
        mode: UsageMode,
        target_name: str | None,
        free_text: str | None,
    ) -> str | None:
        settings = (item.get("attributes") or {}).get("settings")
        texts: list[str] = []
        if isinstance(settings, str):
            texts.append(settings)
        elif settings is not None:
            texts.append(str(settings))
        blob = "\n".join(texts)

        if mode == "freeText":
            needle = (free_text or "").casefold()
            if needle and needle in blob.casefold():
                return "settingsText"
            return None

        if not target_name:
            return None
        hits = extract_data_element_reference_hits(*texts)
        target = target_name.casefold()
        for hit in hits:
            if str(hit.get("name") or "").casefold() == target:
                return str(hit.get("detectionMethod") or "token")
        return None

    async def _rules_for_component(self, component_id: str) -> list[dict[str, Any]]:
        try:
            payload = await self._reactor.get(f"/rule_components/{component_id}/rules")
        except ReactorApiError:
            return []
        return as_list(payload)

    @staticmethod
    def _component_summary(component: dict[str, Any], detection_method: str) -> dict[str, Any]:
        attributes = component.get("attributes") or {}
        row: dict[str, Any] = {
            "id": component.get("id"),
            "name": attributes.get("name"),
            "detectionMethod": detection_method,
        }
        delegate = attributes.get("delegate_descriptor_id")
        if delegate:
            row["delegateDescriptorId"] = delegate
            parts = str(delegate).split("::")
            if len(parts) >= 2:
                row["componentKind"] = parts[1]
        return row

    async def _resolve_cached(
        self,
        *,
        collection: str,
        resource_id: str,
        head_item: dict[str, Any] | None,
        resolved_cache: dict[str, Any],
        lock: asyncio.Lock,
    ) -> Any | None:
        cache_key = f"{collection}:{resource_id}"
        async with lock:
            if cache_key in resolved_cache:
                return resolved_cache[cache_key]
        if self._revision_service is None:
            return None
        try:
            resolved = await self._revision_service.resolve_versions(
                collection,
                resource_id,
                head_item=head_item,
            )
        except ReactorApiError:
            return None
        head_key = str(resolved.head_item.get("id") or "")
        live_key = (
            str(resolved.live_item.get("id") or "") if resolved.live_item else None
        )
        async with lock:
            for key in {resource_id, head_key, live_key}:
                if key:
                    resolved_cache[f"{collection}:{key}"] = resolved
        return resolved

    def _scoped_ids(
        self,
        *,
        resolved: Any,
        version_scope: VersionScope,
    ) -> tuple[str | None, int | None]:
        head = resolved.head_item
        head_id = str(head.get("id") or "")
        live = resolved.live_item
        if version_scope == "live":
            if not live:
                return None, None
            live_id = str(live.get("id") or "")
            if not live_id:
                return None, None
            return live_id, resolved.version_for_item(live)
        return head_id, resolved.latest_version

    async def _components_for_rule(self, rule_id: str) -> list[dict[str, Any]]:
        try:
            return await fetch_all_list_pages(
                self._reactor,
                f"/rules/{rule_id}/rule_components",
                page_size=50,
                max_pages=2,
            )
        except ReactorApiError:
            return []

    async def _build_consumers(
        self,
        *,
        verified_hits: list[dict[str, Any]],
        version_scope: VersionScope,
        detail: UsageDetail,
        mode: UsageMode,
        target_name: str | None,
        free_text: str | None,
        exclude_data_element_id: str | None,
        library_member_ids: set[str] | None,
    ) -> list[dict[str, Any]]:
        if not verified_hits or self._revision_service is None:
            return []

        sem = asyncio.Semaphore(self._concurrency)
        resolved_cache: dict[str, Any] = {}
        cache_lock = asyncio.Lock()

        # Dedupe rule-component hits by component origin before /rules fan-out.
        component_by_origin: dict[str, dict[str, Any]] = {}
        de_hits: list[dict[str, Any]] = []
        extension_hits: list[dict[str, Any]] = []
        for hit in verified_hits:
            if hit.get("type") == "rule_components":
                origin = self._canonical_origin_id(hit) or str(hit.get("id") or "")
                if origin and origin not in component_by_origin:
                    component_by_origin[origin] = hit
            elif hit.get("type") == "data_elements":
                de_hits.append(hit)
            elif hit.get("type") == "extensions":
                extension_hits.append(hit)

        async def _map_component(origin_id: str, hit: dict[str, Any]) -> list[tuple[dict, dict, str]]:
            detection = str(hit["_detectionMethod"])
            async with sem:
                # Prefer origin working component for /rules when available.
                rules = await self._rules_for_component(str(hit.get("id") or origin_id))
            rows: list[tuple[dict, dict, str]] = []
            for rule in rules:
                rows.append((hit, rule, detection))
            return rows

        mapped_lists = await asyncio.gather(
            *[
                _map_component(origin_id, hit)
                for origin_id, hit in list(component_by_origin.items())[: self._max_hits_to_process]
            ]
        )
        component_rule_rows = [row for group in mapped_lists for row in group]

        rule_families: dict[str, dict[str, Any]] = {}
        de_families: dict[str, dict[str, Any]] = {}
        extension_families: dict[str, dict[str, Any]] = {}

        async def _ingest_rule(hit: dict[str, Any], rule: dict[str, Any], detection: str) -> None:
            rule_id = str(rule.get("id") or "")
            if not rule_id:
                return
            async with sem:
                resolved = await self._resolve_cached(
                    collection="rules",
                    resource_id=rule_id,
                    head_item=rule,
                    resolved_cache=resolved_cache,
                    lock=cache_lock,
                )
            if resolved is None:
                return
            head_id = str(resolved.head_item.get("id") or "")
            scoped_id, version = self._scoped_ids(resolved=resolved, version_scope=version_scope)
            if not scoped_id:
                return
            if library_member_ids is not None:
                if head_id not in library_member_ids and scoped_id not in library_member_ids:
                    # Also allow if the hit's owning rule revision is a library member.
                    if rule_id not in library_member_ids:
                        return
            family = rule_families.setdefault(
                head_id,
                {
                    "resolved": resolved,
                    "scoped_id": scoped_id,
                    "version": version,
                    "methods": set(),
                    "scoped_hits": [],
                    "needs_confirm": False,
                },
            )
            family["methods"].add(detection)
            if rule_id == scoped_id:
                family["scoped_hits"].append((hit, detection))
            else:
                family["needs_confirm"] = True

        await asyncio.gather(
            *[_ingest_rule(hit, rule, detection) for hit, rule, detection in component_rule_rows]
        )

        # Bound family count for confirm/resolve cost.
        if len(rule_families) > self._max_families:
            # Keep alphabetical stable subset; truncated signal handled by caller notes.
            keep = sorted(rule_families.keys())[: self._max_families]
            rule_families = {key: rule_families[key] for key in keep}

        async def _ingest_de(hit: dict[str, Any]) -> None:
            de_id = str(hit.get("id") or "")
            if not de_id:
                return
            detection = str(hit["_detectionMethod"])
            async with sem:
                resolved = await self._resolve_cached(
                    collection="data_elements",
                    resource_id=de_id,
                    head_item=hit,
                    resolved_cache=resolved_cache,
                    lock=cache_lock,
                )
            if resolved is None:
                return
            head_id = str(resolved.head_item.get("id") or "")
            if exclude_data_element_id and head_id == exclude_data_element_id:
                return
            scoped_id, version = self._scoped_ids(resolved=resolved, version_scope=version_scope)
            if not scoped_id:
                return
            if library_member_ids is not None:
                if head_id not in library_member_ids and scoped_id not in library_member_ids:
                    if de_id not in library_member_ids:
                        return
            family = de_families.setdefault(
                head_id,
                {
                    "resolved": resolved,
                    "scoped_id": scoped_id,
                    "version": version,
                    "methods": set(),
                    "scoped_hit": None,
                    "needs_confirm": False,
                },
            )
            family["methods"].add(detection)
            if de_id == scoped_id:
                family["scoped_hit"] = hit
            else:
                family["needs_confirm"] = True

        await asyncio.gather(*[_ingest_de(hit) for hit in de_hits[: self._max_hits_to_process]])

        async def _ingest_extension(hit: dict[str, Any]) -> None:
            ext_id = str(hit.get("id") or "")
            if not ext_id:
                return
            detection = str(hit["_detectionMethod"])
            async with sem:
                resolved = await self._resolve_cached(
                    collection="extensions",
                    resource_id=ext_id,
                    head_item=hit,
                    resolved_cache=resolved_cache,
                    lock=cache_lock,
                )
            if resolved is None:
                return
            head_id = str(resolved.head_item.get("id") or "")
            scoped_id, version = self._scoped_ids(resolved=resolved, version_scope=version_scope)
            if not scoped_id:
                return
            if library_member_ids is not None:
                if head_id not in library_member_ids and scoped_id not in library_member_ids:
                    if ext_id not in library_member_ids:
                        return
            family = extension_families.setdefault(
                head_id,
                {
                    "resolved": resolved,
                    "scoped_id": scoped_id,
                    "version": version,
                    "methods": set(),
                    "scoped_hit": None,
                    "needs_confirm": False,
                },
            )
            family["methods"].add(detection)
            if ext_id == scoped_id:
                family["scoped_hit"] = hit
            else:
                family["needs_confirm"] = True

        await asyncio.gather(
            *[_ingest_extension(hit) for hit in extension_hits[: self._max_hits_to_process]]
        )

        async def _finalize_rule(head_id: str, family: dict[str, Any]) -> dict[str, Any] | None:
            resolved = family["resolved"]
            scoped_id = family["scoped_id"]
            methods: set[str] = set(family["methods"])
            scoped_components: list[tuple[dict[str, Any], str]] = list(family["scoped_hits"])

            if not scoped_components and family["needs_confirm"]:
                async with sem:
                    components = await self._components_for_rule(scoped_id)
                for component in components:
                    detection = self._verify_hit(
                        {**component, "type": "rule_components"},
                        mode=mode,
                        target_name=target_name,
                        free_text=free_text,
                    )
                    if detection:
                        scoped_components.append((component, detection))
                        methods.add(detection)

            if not scoped_components:
                # Fast path: for freeText/summary, trust family if any verified hit existed.
                # Still require confirm for dataElement mode when live/latest must match.
                if mode == "freeText" and family["needs_confirm"] and detail == "summary":
                    methods = set(family["methods"])
                else:
                    return None
                if not methods:
                    return None

            head_attrs = resolved.head_item.get("attributes") or {}
            preferred = (
                "token"
                if "token" in methods
                else "customCode"
                if "customCode" in methods
                else "settingsText"
                if "settingsText" in methods
                else next(iter(methods))
            )
            row: dict[str, Any] = {
                "resourceType": "rule",
                "id": scoped_id,
                "headId": head_id,
                "name": head_attrs.get("name"),
                "enabled": head_attrs.get("enabled"),
                "version": family["version"],
                "detectionMethod": preferred,
                "publishState": resolved.publish_state,
            }
            if detail == "components" and scoped_components:
                by_id: dict[str, dict[str, Any]] = {}
                for component, detection in scoped_components:
                    summary = self._component_summary(component, detection)
                    cid = str(summary.get("id") or "")
                    if cid and cid not in by_id:
                        by_id[cid] = summary
                row["components"] = list(by_id.values())
                row["componentCount"] = len(row["components"])
            return row

        rule_rows = await asyncio.gather(
            *[_finalize_rule(head_id, family) for head_id, family in rule_families.items()]
        )

        async def _finalize_de(head_id: str, family: dict[str, Any]) -> dict[str, Any] | None:
            resolved = family["resolved"]
            scoped_id = family["scoped_id"]
            methods = set(family["methods"])
            confirmed = family["scoped_hit"] is not None

            if not confirmed and family["needs_confirm"]:
                if mode == "freeText" and detail == "summary":
                    confirmed = True
                else:
                    async with sem:
                        try:
                            payload = await self._reactor.get(f"/data_elements/{scoped_id}")
                            scoped_item = payload.get("data")
                        except ReactorApiError:
                            scoped_item = None
                    if isinstance(scoped_item, dict):
                        detection = self._verify_hit(
                            {**scoped_item, "type": "data_elements"},
                            mode=mode,
                            target_name=target_name,
                            free_text=free_text,
                        )
                        if detection:
                            confirmed = True
                            methods.add(detection)

            if not confirmed:
                return None
            if exclude_data_element_id and head_id == exclude_data_element_id:
                return None

            head_attrs = resolved.head_item.get("attributes") or {}
            preferred = (
                "token"
                if "token" in methods
                else "customCode"
                if "customCode" in methods
                else "settingsText"
                if "settingsText" in methods
                else next(iter(methods))
            )
            return {
                "resourceType": "dataElement",
                "id": scoped_id,
                "headId": head_id,
                "name": head_attrs.get("name"),
                "enabled": head_attrs.get("enabled"),
                "version": family["version"],
                "detectionMethod": preferred,
                "publishState": resolved.publish_state,
            }

        de_rows = await asyncio.gather(
            *[_finalize_de(head_id, family) for head_id, family in de_families.items()]
        )

        async def _finalize_extension(
            head_id: str, family: dict[str, Any]
        ) -> dict[str, Any] | None:
            resolved = family["resolved"]
            scoped_id = family["scoped_id"]
            methods = set(family["methods"])
            confirmed = family["scoped_hit"] is not None

            if not confirmed and family["needs_confirm"]:
                if mode == "freeText" and detail == "summary":
                    confirmed = True
                else:
                    async with sem:
                        try:
                            payload = await self._reactor.get(f"/extensions/{scoped_id}")
                            scoped_item = payload.get("data")
                        except ReactorApiError:
                            scoped_item = None
                    if isinstance(scoped_item, dict):
                        detection = self._verify_hit(
                            {**scoped_item, "type": "extensions"},
                            mode=mode,
                            target_name=target_name,
                            free_text=free_text,
                        )
                        if detection:
                            confirmed = True
                            methods.add(detection)

            if not confirmed:
                return None

            head_attrs = resolved.head_item.get("attributes") or {}
            preferred = (
                "token"
                if "token" in methods
                else "customCode"
                if "customCode" in methods
                else "settingsText"
                if "settingsText" in methods
                else next(iter(methods))
            )
            display_name = head_attrs.get("display_name") or head_attrs.get("name")
            return {
                "resourceType": "extension",
                "id": scoped_id,
                "headId": head_id,
                "name": display_name,
                "enabled": head_attrs.get("enabled"),
                "version": family["version"],
                "detectionMethod": preferred,
                "publishState": resolved.publish_state,
            }

        extension_rows = await asyncio.gather(
            *[
                _finalize_extension(head_id, family)
                for head_id, family in extension_families.items()
            ]
        )

        consumers = [row for row in [*rule_rows, *de_rows, *extension_rows] if row]
        type_rank = {"rule": 0, "dataElement": 1, "extension": 2}
        consumers.sort(
            key=lambda row: (
                type_rank.get(str(row.get("resourceType") or ""), 9),
                str(row.get("name") or row.get("id") or "").casefold(),
            )
        )
        return consumers
