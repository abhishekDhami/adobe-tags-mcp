from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.adobe.important_revisions import (
    RevisionView,
    annotate_and_filter_revisions,
    present_important_revision_history,
)
from app.adobe.jsonapi import eq_filter, relationship_id
from app.adobe.list_pages import fetch_all_list_pages
from app.adobe.revision_logic import (
    derive_publish_state,
    derive_revision_published,
    latest_version_number,
    pick_live_revision,
    revision_is_live,
    revision_snapshot_summary,
)
from app.adobe.reactor_client import ReadOnlyReactorClient, ReactorApiError
from app.presenters.revision import present_version_summary
from app.services.resource_helpers import fetch_resource_with_meta

_RESOURCE_CONFIG: dict[str, dict[str, str]] = {
    "rules": {
        "kind": "rule",
        "fetch_path": "/rules/{id}",
        "revisions_path": "/rules/{id}/revisions",
        "not_found": "Rule {id} was not found.",
    },
    "data_elements": {
        "kind": "dataElement",
        "fetch_path": "/data_elements/{id}",
        "revisions_path": "/data_elements/{id}/revisions",
        "not_found": "Data element {id} was not found.",
    },
    "extensions": {
        "kind": "extension",
        "fetch_path": "/extensions/{id}",
        "revisions_path": "/extensions/{id}/revisions",
        "not_found": "Extension {id} was not found.",
    },
}

_MAX_REVISION_ITEMS = 500


@dataclass(frozen=True)
class ResourceRevisionTarget:
    collection: str
    resource_id: str


@dataclass
class ResolvedVersions:
    head_item: dict[str, Any]
    revisions: list[dict[str, Any]]
    live_item: dict[str, Any] | None
    live_resolution_method: str
    publish_state: str
    latest_version: int
    revisions_truncated: bool

    @property
    def version_summary(self) -> dict[str, Any]:
        head_is_live = revision_is_live(
            self.head_item,
            self.live_item,
            self.head_item,
            self.revisions,
        )
        latest_snapshot = revision_snapshot_summary(
            self.head_item,
            version=self.latest_version,
            is_live=head_is_live,
            published=(self.publish_state == "live"),
        )
        live_snapshot = None
        if self.live_item is not None:
            live_snapshot = revision_snapshot_summary(
                self.live_item,
                is_live=True,
                published=True,
            )
        return present_version_summary(
            publish_state=self.publish_state,
            latest=latest_snapshot,
            live=live_snapshot,
            live_resolution_method=self.live_resolution_method,
            revisions_truncated=self.revisions_truncated,
        )

    def version_for_item(self, item: dict[str, Any]) -> int:
        """UI revision number for the requested resource (head → latest; revision → its number)."""
        if item.get("id") == self.head_item.get("id"):
            return self.latest_version

        item_id = item.get("id")
        # Prefer the matching row in /revisions — GET of a revision often still carries
        # meta.latest_revision_number for the whole family, which must not win here.
        for rev in self.revisions:
            if rev.get("id") == item_id:
                rev_num = (rev.get("attributes") or {}).get("revision_number")
                if isinstance(rev_num, int) and rev_num > 0:
                    return rev_num
                break

        rev_num = (item.get("attributes") or {}).get("revision_number")
        if isinstance(rev_num, int) and rev_num > 0:
            return rev_num
        return self.latest_version

    def published_for_item(self, item: dict[str, Any]) -> bool:
        """Whether the requested revision was deployed (live now or previously).

        Not "was this component ever published" — pending working copies are false even
        when older revisions were deployed.
        """
        is_live = revision_is_live(item, self.live_item, self.head_item, self.revisions)
        if is_live:
            return True

        item_id = item.get("id")
        for rev in self.revisions:
            if rev.get("id") == item_id:
                return derive_revision_published(rev, is_live=False)

        # Head / working copy: only published when it is the live revision.
        if item_id == self.head_item.get("id"):
            return self.publish_state == "live"

        return derive_revision_published(item, is_live=False)


class RevisionService:
    def __init__(self, reactor: ReadOnlyReactorClient, max_revision_pages: int = 10):
        self._reactor = reactor
        self._max_revision_pages = max_revision_pages

    def _target(self, collection: str, resource_id: str) -> ResourceRevisionTarget:
        if collection not in _RESOURCE_CONFIG:
            raise ValueError(f"Unsupported resource collection: {collection}")
        return ResourceRevisionTarget(collection=collection, resource_id=resource_id)

    async def _fetch_head(self, target: ResourceRevisionTarget) -> dict[str, Any]:
        config = _RESOURCE_CONFIG[target.collection]
        item, _ = await fetch_resource_with_meta(
            self._reactor,
            config["fetch_path"].format(id=target.resource_id),
            not_found_message=config["not_found"].format(id=target.resource_id),
        )
        return item

    async def _fetch_revisions(self, target: ResourceRevisionTarget) -> tuple[list[dict[str, Any]], bool]:
        config = _RESOURCE_CONFIG[target.collection]
        revisions = await fetch_all_list_pages(
            self._reactor,
            config["revisions_path"].format(id=target.resource_id),
            page_size=50,
            max_pages=self._max_revision_pages,
        )
        truncated = len(revisions) >= _MAX_REVISION_ITEMS
        return revisions, truncated

    def _canonical_head_id(self, item: dict[str, Any], fallback_id: str) -> str:
        """Prefer Adobe origin (true head) when the fetched item is a revision snapshot."""
        origin_id = relationship_id(item, "origin")
        if origin_id:
            return origin_id
        return str(item.get("id") or fallback_id)

    def _resolve_from_loaded(
        self,
        head_item: dict[str, Any],
        revisions: list[dict[str, Any]],
        *,
        revisions_truncated: bool = False,
    ) -> ResolvedVersions:
        live_item, live_method = pick_live_revision(head_item, revisions)
        latest_version = latest_version_number(head_item, revisions)
        publish_state = derive_publish_state(head_item, live_item, revisions)
        return ResolvedVersions(
            head_item=head_item,
            revisions=revisions,
            live_item=live_item,
            live_resolution_method=live_method,
            publish_state=publish_state,
            latest_version=latest_version,
            revisions_truncated=revisions_truncated,
        )

    async def resolve_versions(
        self,
        collection: str,
        resource_id: str,
        *,
        head_item: dict[str, Any] | None = None,
    ) -> ResolvedVersions:
        """Resolve latest/live for a resource family.

        ``resource_id`` / ``head_item`` may be the working head **or** a revision snapshot
        (e.g. live revision id from review-development-library). Always canonicalizes to
        the origin/head before computing versions.latest / versions.live.
        """
        target = self._target(collection, resource_id)
        loaded = head_item or await self._fetch_head(target)
        canonical_id = self._canonical_head_id(loaded, resource_id)
        canonical_target = self._target(collection, canonical_id)

        if str(loaded.get("id") or "") != canonical_id:
            true_head = await self._fetch_head(canonical_target)
        else:
            true_head = loaded

        revisions, truncated = await self._fetch_revisions(canonical_target)
        return self._resolve_from_loaded(true_head, revisions, revisions_truncated=truncated)

    async def _development_library_member_ids(
        self,
        *,
        property_id: str,
        collection: str,
    ) -> tuple[set[str], str]:
        """Revision/head ids in any development library.

        Returns (ids, status) where status is ok | failed | partial.
        """
        member_path = {
            "rules": "rules",
            "data_elements": "data_elements",
            "extensions": "extensions",
        }[collection]
        try:
            libraries = await fetch_all_list_pages(
                self._reactor,
                f"/properties/{property_id}/libraries",
                params={"filter[state]": eq_filter("development")},
                page_size=50,
                max_pages=5,
            )
        except ReactorApiError:
            return set(), "failed"

        member_ids: set[str] = set()
        saw_member_failure = False
        for library in libraries:
            library_id = library.get("id")
            if not library_id:
                continue
            try:
                members = await fetch_all_list_pages(
                    self._reactor,
                    f"/libraries/{library_id}/{member_path}",
                    page_size=50,
                    max_pages=10,
                )
            except ReactorApiError:
                saw_member_failure = True
                continue
            for member in members:
                member_id = member.get("id")
                if member_id:
                    member_ids.add(str(member_id))
        if saw_member_failure:
            return member_ids, "partial"
        return member_ids, "ok"

    async def list_revision_history(
        self,
        collection: str,
        resource_id: str,
        *,
        view: RevisionView = "important",
    ) -> dict[str, Any]:
        if view not in {"important", "full"}:
            view = "important"

        resolved = await self.resolve_versions(collection, resource_id)
        config = _RESOURCE_CONFIG[collection]
        head_item = resolved.head_item
        head_attributes = head_item.get("attributes") or {}
        name = head_attributes.get("name") or head_attributes.get("display_name")
        head_id = str(head_item.get("id") or resource_id)

        property_id = relationship_id(head_item, "property")
        development_ids: set[str] = set()
        development_lookup_status = "ok"
        if property_id:
            development_ids, development_lookup_status = await self._development_library_member_ids(
                property_id=property_id,
                collection=collection,
            )

        # failed → omit both lib roles; partial → keep found in-lib, never invent headNotInDev
        include_in_dev = development_lookup_status in {"ok", "partial"}
        include_head_not_in_dev = development_lookup_status == "ok"
        visible, important_count, full_count = annotate_and_filter_revisions(
            head_item=head_item,
            revisions=resolved.revisions,
            live_item=resolved.live_item,
            development_library_revision_ids=development_ids,
            view=view,
            include_in_development_library_role=include_in_dev,
            include_head_not_in_dev_library_role=include_head_not_in_dev,
        )

        result = present_important_revision_history(
            resource_kind=config["kind"],
            head_id=head_id,
            name=str(name) if name else None,
            view=view,
            visible_revisions=visible,
            important_count=important_count,
            full_revision_count=full_count,
        )
        if property_id:
            result["propertyId"] = property_id
        warnings: list[str] = []
        if development_lookup_status != "ok":
            result["developmentLibraryLookupIncomplete"] = True
            warnings.append(
                "Development library membership lookup was incomplete; "
                "inDevelopmentLibrary / headNotInDevLibrary roles were omitted."
            )
        if resolved.revisions_truncated:
            result["revisionsTruncated"] = True
            warnings.append(
                f"Revision history reached the scan limit ({_MAX_REVISION_ITEMS} items). "
                "Older revisions may be missing."
            )
        if warnings:
            result["warning"] = " ".join(warnings)
        if view == "important" and important_count < full_count:
            result["narrative"] = (
                f"Showing {important_count} important revision(s) of {full_count} total. "
                "Pass view=full to include every revision."
            )
        elif view == "full":
            result["narrative"] = (
                f"Showing all {full_count} revision(s). "
                f"{important_count} marked important=true with roles."
            )
        return result

    async def list_rule_revisions(
        self, rule_id: str, *, view: RevisionView = "important"
    ) -> dict[str, Any]:
        return await self.list_revision_history("rules", rule_id, view=view)

    async def list_data_element_revisions(
        self, data_element_id: str, *, view: RevisionView = "important"
    ) -> dict[str, Any]:
        return await self.list_revision_history("data_elements", data_element_id, view=view)

    async def list_extension_revisions(
        self, extension_id: str, *, view: RevisionView = "important"
    ) -> dict[str, Any]:
        return await self.list_revision_history("extensions", extension_id, view=view)
