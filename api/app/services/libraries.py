from __future__ import annotations

import asyncio
from typing import Any, Literal

from app.adobe.list_pages import fetch_all_list_pages
from app.adobe.jsonapi import as_list, clamp_page, eq_filter, paginate_meta, reactor_page_number, relationship_id, resource_meta
from app.adobe.reactor_client import ReadOnlyReactorClient, ReactorApiError
from app.adobe.revision_logic import revision_version
from app.presenters import (
    ViewOptions,
    extension_summary_from_item,
    present_data_element,
    present_extension,
    present_rule,
)
from app.presenters.library import (
    DevLibraryReviewDepth,
    classify_dev_library_change,
    present_ambiguous_libraries,
    present_development_library_review,
    present_dev_library_change_row,
    present_dev_library_side,
    present_environment_index,
    present_library_detail,
    present_library_index,
    present_library_resource_row,
)
from app.presenters.lists import property_summary
from app.services.resource_helpers import fetch_resource_with_meta, resolve_resource_version
from app.services.revisions import RevisionService

LibraryResourceFilter = Literal["all", "rules", "data_elements", "extensions"]

_REVISION_PATHS = {
    "rules": "/rules/{id}/revisions",
    "data_elements": "/data_elements/{id}/revisions",
    "extensions": "/extensions/{id}/revisions",
}

_ROW_TYPES = {
    "rules": "rule",
    "data_elements": "dataElement",
    "extensions": "extension",
}

_COLLECTION_PATH = {
    "rules": "rules",
    "data_elements": "data_elements",
    "extensions": "extensions",
}


class LibrariesService:
    def __init__(
        self,
        reactor: ReadOnlyReactorClient,
        default_page_size: int,
        max_page_size: int,
        revision_service: RevisionService | None = None,
    ):
        self._reactor = reactor
        self._default_page_size = default_page_size
        self._max_page_size = max_page_size
        self._revision_service = revision_service

    async def _fetch_environment_summary(self, environment_id: str) -> dict[str, Any] | None:
        try:
            item, _ = await fetch_resource_with_meta(
                self._reactor,
                f"/environments/{environment_id}",
                not_found_message=f"Environment {environment_id} was not found.",
            )
            attributes = item.get("attributes") or {}
            return {
                "id": item.get("id"),
                "name": attributes.get("name"),
                "stage": attributes.get("stage"),
            }
        except ReactorApiError:
            return {"id": environment_id}

    async def _hydrate_library_environments(self, libraries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        env_ids: set[str] = set()
        for library in libraries:
            env_id = relationship_id(library, "environment")
            if env_id:
                env_ids.add(env_id)
        lookup: dict[str, dict[str, Any]] = {}
        for env_id in env_ids:
            summary = await self._fetch_environment_summary(env_id)
            if summary:
                lookup[env_id] = summary
        return lookup

    async def list_environments(self, property_id: str) -> dict[str, Any]:
        payload = await self._reactor.get(f"/properties/{property_id}/environments")
        items = [present_environment_index(item) for item in as_list(payload)]
        return {"items": items, "totalCount": len(items)}

    async def list_published_libraries(
        self,
        property_id: str,
        *,
        page: int = 1,
        page_size: int = 0,
        state: str = "published",
        environment_id: str | None = None,
        sort: str = "-published_at",
    ) -> dict[str, Any]:
        page, page_size = clamp_page(page, page_size, self._default_page_size, self._max_page_size)
        params: dict[str, Any] = {
            "page[size]": page_size,
            "page[number]": reactor_page_number(page),
            "filter[state]": eq_filter(state),
            "sort": sort,
        }
        payload = await self._reactor.get(f"/properties/{property_id}/libraries", params=params)
        libraries = as_list(payload)
        env_lookup = await self._hydrate_library_environments(libraries)
        items = []
        for library in libraries:
            env_id = relationship_id(library, "environment")
            if environment_id and env_id != environment_id:
                continue
            environment = env_lookup.get(env_id) if env_id else None
            items.append(present_library_index(library, environment=environment))
        if environment_id:
            total = len(items)
        else:
            total = int((payload.get("meta") or {}).get("pagination", {}).get("total_count", len(items)))
        return {"items": items, "pagination": paginate_meta(page, page_size, total)}

    async def get_development_library(self, property_id: str) -> dict[str, Any]:
        libraries = await fetch_all_list_pages(
            self._reactor,
            f"/properties/{property_id}/libraries",
            params={"filter[state]": eq_filter("development")},
            page_size=50,
            max_pages=5,
        )
        if not libraries:
            raise ReactorApiError(
                "NOT_FOUND",
                f"No development library found for property {property_id}.",
                404,
            )
        env_lookup = await self._hydrate_library_environments(libraries)
        if len(libraries) == 1:
            library = libraries[0]
            env_id = relationship_id(library, "environment")
            return {
                "status": "resolved",
                "library": present_library_index(library, environment=env_lookup.get(env_id) if env_id else None),
            }
        candidates = []
        for library in libraries:
            env_id = relationship_id(library, "environment")
            candidates.append(
                present_library_index(library, environment=env_lookup.get(env_id) if env_id else None)
            )
        return present_ambiguous_libraries(
            message="Multiple development libraries match. Ask the user which library to review.",
            candidates=candidates,
        )

    async def get_library(self, library_id: str) -> dict[str, Any]:
        item, item_meta = await fetch_resource_with_meta(
            self._reactor,
            f"/libraries/{library_id}",
            not_found_message=f"Library {library_id} was not found.",
        )
        environment: dict[str, Any] | None = None
        env_id = relationship_id(item, "environment")
        if env_id:
            environment = await self._fetch_environment_summary(env_id)
        property_ref: dict[str, Any] | None = None
        property_id = relationship_id(item, "property")
        if property_id:
            try:
                prop_item, _ = await fetch_resource_with_meta(
                    self._reactor,
                    f"/properties/{property_id}",
                    not_found_message=f"Property {property_id} was not found.",
                )
                property_ref = property_summary(prop_item)
            except ReactorApiError:
                property_ref = {"id": property_id}
        return present_library_detail(
            item,
            environment=environment,
            property_summary=property_ref,
            item_meta=item_meta,
        )

    async def _present_library_resource(
        self,
        item: dict[str, Any],
        *,
        collection: str,
    ) -> dict[str, Any]:
        resource_id = str(item.get("id"))
        item_meta = resource_meta(item)
        revision_path = _REVISION_PATHS[collection].format(id=resource_id)
        version = await resolve_resource_version(
            self._reactor,
            revision_path,
            resource_meta_dict=item_meta,
        )
        return present_library_resource_row(
            item,
            resource_type=_ROW_TYPES[collection],  # type: ignore[arg-type]
            version=version,
        )

    def _member_head_id(self, item: dict[str, Any]) -> str:
        origin_id = relationship_id(item, "origin")
        if origin_id:
            return origin_id
        return str(item.get("id"))

    async def _hydrate_extensions(self, extension_ids: set[str]) -> dict[str, dict[str, Any]]:
        lookup: dict[str, dict[str, Any]] = {}
        for extension_id in extension_ids:
            try:
                item, _ = await fetch_resource_with_meta(
                    self._reactor,
                    f"/extensions/{extension_id}",
                    not_found_message=f"Extension {extension_id} was not found.",
                )
                lookup[extension_id] = extension_summary_from_item(item)
            except ReactorApiError:
                lookup[extension_id] = {"id": extension_id, "error": "unavailable"}
        return lookup

    async def _present_full_side(
        self,
        *,
        collection: str,
        item: dict[str, Any],
        version: int | None,
    ) -> dict[str, Any]:
        options = ViewOptions(depth="full", include_code=True)
        if collection == "rules":
            components = await fetch_all_list_pages(
                self._reactor,
                f"/rules/{item.get('id')}/rule_components",
                page_size=50,
                max_pages=5,
            )
            extension_ids = {
                eid
                for component in components
                if (eid := relationship_id(component, "extension"))
            }
            extension_lookup = await self._hydrate_extensions(extension_ids)
            return present_rule(
                item,
                options=options,
                components=components,
                extension_lookup=extension_lookup,
                version=version or 0,
            )
        if collection == "data_elements":
            return present_data_element(item, options=options, version=version or 0)
        return present_extension(item, options=options, version=version or 0)

    async def _build_dev_library_change(
        self,
        *,
        collection: str,
        member: dict[str, Any],
        depth: DevLibraryReviewDepth,
    ) -> dict[str, Any] | None:
        if self._revision_service is None:
            raise ReactorApiError(
                "REVISION_SERVICE_UNAVAILABLE",
                "Revision service is required for development library review.",
                500,
            )

        head_id = self._member_head_id(member)
        resolved = await self._revision_service.resolve_versions(collection, head_id)
        pending_item = member
        live_item = resolved.live_item
        change_kind = classify_dev_library_change(live_item=live_item, pending_item=pending_item)
        if change_kind is None:
            return None

        pending_version = revision_version(pending_item)
        if pending_version is None and pending_item.get("id") == resolved.head_item.get("id"):
            pending_version = resolved.latest_version

        pending_detail = None
        live_detail = None
        if depth == "full":
            pending_detail = await self._present_full_side(
                collection=collection,
                item=pending_item,
                version=pending_version,
            )
            if live_item is not None and change_kind != "new":
                live_detail = await self._present_full_side(
                    collection=collection,
                    item=live_item,
                    version=revision_version(live_item),
                )

        pending_side = present_dev_library_side(
            pending_item,
            version=pending_version,
            detail=pending_detail,
        )
        published_live_side = None
        if live_item is not None and change_kind != "new":
            published_live_side = present_dev_library_side(
                live_item,
                version=revision_version(live_item),
                detail=live_detail,
            )

        attributes = pending_item.get("attributes") or {}
        name = attributes.get("name") or attributes.get("display_name")
        return present_dev_library_change_row(
            change_kind=change_kind,
            resource_kind=_ROW_TYPES[collection],  # type: ignore[arg-type]
            name=str(name) if name else None,
            pending=pending_side,
            published_live=published_live_side,
        )

    async def review_development_library(
        self,
        library_id: str,
        *,
        depth: DevLibraryReviewDepth = "summary",
    ) -> dict[str, Any]:
        if depth not in {"summary", "full"}:
            raise ReactorApiError(
                "INVALID_DEPTH",
                "depth must be 'summary' or 'full'.",
                400,
            )
        if self._revision_service is None:
            raise ReactorApiError(
                "REVISION_SERVICE_UNAVAILABLE",
                "Revision service is required for development library review.",
                500,
            )

        library_item, item_meta = await fetch_resource_with_meta(
            self._reactor,
            f"/libraries/{library_id}",
            not_found_message=f"Library {library_id} was not found.",
        )
        library_state = (library_item.get("attributes") or {}).get("state")
        if library_state != "development":
            state_label = str(library_state) if library_state else "unknown"
            raise ReactorApiError(
                "NOT_A_DEVELOPMENT_LIBRARY",
                (
                    "This endpoint is only for reviewing development libraries. "
                    f"Library {library_id} has state '{state_label}'. "
                    "Use GET .../properties/{propertyId}/development-libraries to resolve a development library."
                ),
                400,
            )
        env_id = relationship_id(library_item, "environment")
        environment = await self._fetch_environment_summary(env_id) if env_id else None
        property_id = relationship_id(library_item, "property")
        property_ref: dict[str, Any] | None = None
        if property_id:
            try:
                prop_item, _ = await fetch_resource_with_meta(
                    self._reactor,
                    f"/properties/{property_id}",
                    not_found_message=f"Property {property_id} was not found.",
                )
                property_ref = property_summary(prop_item)
            except ReactorApiError:
                property_ref = {"id": property_id}

        library = present_library_detail(
            library_item,
            environment=environment,
            property_summary=property_ref,
            item_meta=item_meta,
        )

        grouped: dict[str, list[dict[str, Any]]] = {
            "rules": [],
            "dataElements": [],
            "extensions": [],
        }
        key_map = {"rules": "rules", "data_elements": "dataElements", "extensions": "extensions"}

        for collection in ("rules", "data_elements", "extensions"):
            members = await fetch_all_list_pages(
                self._reactor,
                f"/libraries/{library_id}/{_COLLECTION_PATH[collection]}",
                page_size=50,
            )
            rows = await asyncio.gather(
                *[
                    self._build_dev_library_change(
                        collection=collection,
                        member=member,
                        depth=depth,
                    )
                    for member in members
                ]
            )
            grouped[key_map[collection]] = [row for row in rows if row is not None]

        return present_development_library_review(
            library=library,
            depth=depth,
            changes=grouped,
        )

    async def list_library_resources(
        self,
        library_id: str,
        *,
        resource_type: LibraryResourceFilter = "all",
        page: int = 1,
        page_size: int = 0,
    ) -> dict[str, Any]:
        page, page_size = clamp_page(page, page_size, self._default_page_size, self._max_page_size)
        collections: list[str] = (
            ["rules", "data_elements", "extensions"]
            if resource_type == "all"
            else [resource_type]
        )
        grouped: dict[str, list[dict[str, Any]]] = {
            "rules": [],
            "dataElements": [],
            "extensions": [],
        }
        key_map = {"rules": "rules", "data_elements": "dataElements", "extensions": "extensions"}

        for collection in collections:
            items = await fetch_all_list_pages(
                self._reactor,
                f"/libraries/{library_id}/{collection}",
                page_size=50,
            )
            rows = await asyncio.gather(
                *[self._present_library_resource(item, collection=collection) for item in items]
            )
            grouped[key_map[collection]] = list(rows)

        if resource_type != "all":
            single_key = key_map[resource_type]
            items = grouped[single_key]
            start = (page - 1) * page_size
            end = start + page_size
            paged = items[start:end]
            return {
                "libraryId": library_id,
                "resourceType": resource_type,
                "items": paged,
                "pagination": paginate_meta(page, page_size, len(items)),
            }

        all_items = grouped["rules"] + grouped["dataElements"] + grouped["extensions"]
        return {
            "libraryId": library_id,
            "resourceType": "all",
            "resources": grouped,
            "totalCount": len(all_items),
        }
