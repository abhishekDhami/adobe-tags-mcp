from __future__ import annotations

from typing import Any

from app.adobe.jsonapi import (
    as_list,
    clamp_page,
    paginate_meta,
    reactor_page_number,
    relationship_id,
    resource_meta,
)
from app.adobe.reactor_client import ReadOnlyReactorClient, ReactorApiError
from app.presenters import (
    ViewOptions,
    extension_summary_from_item,
    present_data_element,
    present_data_element_index,
    present_extension,
    present_extension_index,
    present_property_index,
    present_rule,
    present_rule_index,
    present_search_index,
    property_summary,
)
from app.services.resource_helpers import resolve_resource_version
from app.services.revisions import RevisionService


class TagsService:
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

    async def _fetch_resource(self, path: str, *, not_found_message: str) -> dict[str, Any]:
        payload = await self._reactor.get(path)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ReactorApiError("NOT_FOUND", not_found_message, 404)
        return data

    async def _fetch_resource_with_meta(
        self, path: str, *, not_found_message: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = await self._reactor.get(path)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ReactorApiError("NOT_FOUND", not_found_message, 404)
        return data, resource_meta(data, payload)

    async def _fetch_rule(self, rule_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        return await self._fetch_resource_with_meta(
            f"/rules/{rule_id}",
            not_found_message=f"Rule {rule_id} was not found.",
        )

    async def _fetch_property_summary(self, property_id: str) -> dict[str, Any] | None:
        try:
            item = await self._fetch_resource(
                f"/properties/{property_id}",
                not_found_message=f"Property {property_id} was not found.",
            )
            return property_summary(item)
        except ReactorApiError:
            return {"id": property_id}

    async def _hydrate_extensions(self, extension_ids: set[str]) -> dict[str, dict[str, Any]]:
        lookup: dict[str, dict[str, Any]] = {}
        for extension_id in extension_ids:
            try:
                item = await self._fetch_resource(
                    f"/extensions/{extension_id}",
                    not_found_message=f"Extension {extension_id} was not found.",
                )
                lookup[extension_id] = extension_summary_from_item(item)
            except ReactorApiError:
                lookup[extension_id] = {"id": extension_id, "error": "unavailable"}
        return lookup

    async def _attach_versions(
        self,
        collection: str,
        resource_id: str,
        view: dict[str, Any],
        *,
        resolved: Any | None = None,
        requested_item: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._revision_service is None:
            return view
        version_state = resolved or await self._revision_service.resolve_versions(collection, resource_id)
        # Keep caller-assigned version (requested revision). Only fill if missing.
        if view.get("version") is None:
            view["version"] = version_state.latest_version
        view["versions"] = version_state.version_summary
        if requested_item is not None:
            view["published"] = version_state.published_for_item(requested_item)
        else:
            view["published"] = version_state.publish_state == "live"
        # publishedAt only when this revision was deployed — never contradict published=false.
        if not view["published"]:
            view.pop("publishedAt", None)
        return view

    def _extension_ids_from_components(self, components: list[dict[str, Any]]) -> set[str]:
        ids: set[str] = set()
        for component in components:
            extension_data = ((component.get("relationships") or {}).get("extension") or {}).get("data")
            if isinstance(extension_data, dict) and extension_data.get("id"):
                ids.add(str(extension_data["id"]))
        return ids

    async def list_properties(self, *, page: int = 1, page_size: int = 0) -> dict[str, Any]:
        page, page_size = clamp_page(page, page_size, self._default_page_size, self._max_page_size)
        companies = as_list(await self._reactor.get("/companies"))
        if not companies:
            return {"items": [], "pagination": paginate_meta(page, page_size, 0)}

        company_id = companies[0]["id"]
        payload = await self._reactor.get(
            f"/companies/{company_id}/properties",
            params={"page[size]": page_size, "page[number]": reactor_page_number(page)},
        )
        items = [present_property_index(item) for item in as_list(payload)]
        total = int((payload.get("meta") or {}).get("pagination", {}).get("total_count", len(items)))
        return {"items": items, "pagination": paginate_meta(page, page_size, total)}

    async def list_rules(
        self,
        property_id: str,
        *,
        page: int = 1,
        page_size: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        page, page_size = clamp_page(page, page_size, self._default_page_size, self._max_page_size)
        params: dict[str, Any] = {"page[size]": page_size, "page[number]": reactor_page_number(page)}
        if search:
            params["filter[name]"] = search
        payload = await self._reactor.get(f"/properties/{property_id}/rules", params=params)
        items = [present_rule_index(item) for item in as_list(payload)]
        total = int((payload.get("meta") or {}).get("pagination", {}).get("total_count", len(items)))
        return {"items": items, "pagination": paginate_meta(page, page_size, total)}

    async def _fetch_rule_components(self, rule_id: str) -> list[dict[str, Any]]:
        payload = await self._reactor.get(f"/rules/{rule_id}/rule_components")
        return as_list(payload)

    async def get_rule(
        self,
        rule_id: str,
        *,
        options: ViewOptions | None = None,
    ) -> dict[str, Any]:
        opts = options or ViewOptions(depth="context")
        item, rule_meta = await self._fetch_rule(rule_id)
        resolved = None
        if self._revision_service is not None:
            resolved = await self._revision_service.resolve_versions("rules", rule_id, head_item=item)
            rule_version = resolved.version_for_item(item)
        else:
            rule_version = await resolve_resource_version(
                self._reactor,
                f"/rules/{rule_id}/revisions",
                resource_meta_dict=rule_meta,
            )

        components: list[dict[str, Any]] | None = None
        extension_lookup: dict[str, dict[str, Any]] = {}
        property_ref: dict[str, Any] | None = None

        if opts.include_logic:
            components = await self._fetch_rule_components(rule_id)
            extension_lookup = await self._hydrate_extensions(self._extension_ids_from_components(components))
            property_id = relationship_id(item, "property")
            if property_id and opts.depth in {"context", "full"}:
                property_ref = await self._fetch_property_summary(property_id)

        return await self._attach_versions(
            "rules",
            rule_id,
            present_rule(
                item,
                options=opts,
                components=components,
                extension_lookup=extension_lookup,
                property_summary=property_ref,
                version=rule_version,
            ),
            resolved=resolved,
            requested_item=item,
        )

    async def list_rule_components(self, rule_id: str) -> dict[str, Any]:
        components = await self._fetch_rule_components(rule_id)
        extension_lookup = await self._hydrate_extensions(self._extension_ids_from_components(components))
        opts = ViewOptions(depth="context")
        item, _ = await self._fetch_rule(rule_id)
        view = present_rule(
            item,
            options=opts,
            components=components,
            extension_lookup=extension_lookup,
            version=0,
        )
        logic = view.get("logic") or {"events": [], "conditions": [], "actions": []}
        flat = logic.get("events", []) + logic.get("conditions", []) + logic.get("actions", [])
        if logic.get("unknown"):
            flat.extend(logic["unknown"])
        return {
            "ruleId": rule_id,
            "logic": logic,
            "totalCount": len(flat),
        }

    async def list_data_elements(
        self,
        property_id: str,
        *,
        page: int = 1,
        page_size: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        page, page_size = clamp_page(page, page_size, self._default_page_size, self._max_page_size)
        params: dict[str, Any] = {"page[size]": page_size, "page[number]": reactor_page_number(page)}
        if search:
            params["filter[name]"] = search
        payload = await self._reactor.get(f"/properties/{property_id}/data_elements", params=params)
        items = [present_data_element_index(item) for item in as_list(payload)]
        total = int((payload.get("meta") or {}).get("pagination", {}).get("total_count", len(items)))
        return {"items": items, "pagination": paginate_meta(page, page_size, total)}

    async def get_data_element(
        self,
        data_element_id: str,
        *,
        options: ViewOptions | None = None,
    ) -> dict[str, Any]:
        opts = options or ViewOptions(depth="detail")
        item, de_meta = await self._fetch_resource_with_meta(
            f"/data_elements/{data_element_id}",
            not_found_message=f"Data element {data_element_id} was not found.",
        )
        property_ref: dict[str, Any] | None = None
        property_id = relationship_id(item, "property")
        if property_id and opts.depth in {"context", "full"}:
            property_ref = await self._fetch_property_summary(property_id)
        resolved = None
        if self._revision_service is not None:
            resolved = await self._revision_service.resolve_versions(
                "data_elements",
                data_element_id,
                head_item=item,
            )
            version = resolved.version_for_item(item)
        else:
            version = await resolve_resource_version(
                self._reactor,
                f"/data_elements/{data_element_id}/revisions",
                resource_meta_dict=de_meta,
            )
        return await self._attach_versions(
            "data_elements",
            data_element_id,
            present_data_element(
                item,
                options=opts,
                property_summary=property_ref,
                version=version,
            ),
            resolved=resolved,
            requested_item=item,
        )

    async def list_extensions(
        self,
        property_id: str,
        *,
        page: int = 1,
        page_size: int = 0,
    ) -> dict[str, Any]:
        page, page_size = clamp_page(page, page_size, self._default_page_size, self._max_page_size)
        payload = await self._reactor.get(
            f"/properties/{property_id}/extensions",
            params={"page[size]": page_size, "page[number]": reactor_page_number(page)},
        )
        items = [present_extension_index(item) for item in as_list(payload)]
        total = int((payload.get("meta") or {}).get("pagination", {}).get("total_count", len(items)))
        return {"items": items, "pagination": paginate_meta(page, page_size, total)}

    async def get_extension(
        self,
        extension_id: str,
        *,
        options: ViewOptions | None = None,
    ) -> dict[str, Any]:
        opts = options or ViewOptions(depth="detail")
        item, ext_meta = await self._fetch_resource_with_meta(
            f"/extensions/{extension_id}",
            not_found_message=f"Extension {extension_id} was not found.",
        )
        property_ref: dict[str, Any] | None = None
        property_id = relationship_id(item, "property")
        if property_id and opts.depth in {"context", "full"}:
            property_ref = await self._fetch_property_summary(property_id)
        resolved = None
        if self._revision_service is not None:
            resolved = await self._revision_service.resolve_versions(
                "extensions",
                extension_id,
                head_item=item,
            )
            version = resolved.version_for_item(item)
        else:
            version = await resolve_resource_version(
                self._reactor,
                f"/extensions/{extension_id}/revisions",
                resource_meta_dict=ext_meta,
            )
        return await self._attach_versions(
            "extensions",
            extension_id,
            present_extension(
                item,
                options=opts,
                property_summary=property_ref,
                version=version,
            ),
            resolved=resolved,
            requested_item=item,
        )

    async def search_resources(
        self,
        *,
        query: str,
        resource_types: list[str] | None = None,
        page: int = 1,
        page_size: int = 0,
    ) -> dict[str, Any]:
        page, page_size = clamp_page(page, page_size, self._default_page_size, self._max_page_size)
        body: dict[str, Any] = {
            "query": {"attributes.name": {"value": query}},
            "from": (page - 1) * page_size,
            "size": page_size,
        }
        if resource_types:
            body["resource_types"] = resource_types
        payload = await self._reactor.search(body)
        items = [present_search_index(item) for item in as_list(payload)]
        total = int((payload.get("meta") or {}).get("total_count", len(items)))
        return {"items": items, "pagination": paginate_meta(page, page_size, total)}
