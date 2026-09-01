from __future__ import annotations

from typing import Any

from pydantic import Field

from .common import StrictModel
from .tags import FlexibleView, Pagination


class EnvironmentSummary(FlexibleView):
    resource_type: str | None = Field(default=None, alias="resourceType")
    id: str | None = None
    name: str | None = None
    stage: str | None = None
    path: str | None = None


class EnvironmentListResult(StrictModel):
    items: list[EnvironmentSummary]
    total_count: int = Field(alias="totalCount")


class LibrarySummary(FlexibleView):
    resource_type: str | None = Field(default=None, alias="resourceType")
    id: str | None = None
    name: str | None = None
    state: str | None = None
    build_required: bool | None = Field(default=None, alias="buildRequired")
    published_at: str | None = Field(default=None, alias="publishedAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")
    environment: dict[str, Any] | None = None


class PaginatedLibraries(StrictModel):
    items: list[LibrarySummary]
    pagination: Pagination


class LibraryDetail(FlexibleView):
    resource_type: str = Field(alias="resourceType")
    id: str | None = None
    name: str | None = None
    state: str | None = None
    build_required: bool | None = Field(default=None, alias="buildRequired")
    environment: dict[str, Any] | None = None
    property: dict[str, Any] | None = None
    narrative: str | None = None


class DevLibraryCandidateResult(FlexibleView):
    status: str
    library: LibrarySummary | None = None
    message: str | None = None
    candidates: list[LibrarySummary] | None = None


class LibraryResourceRow(FlexibleView):
    resource_type: str = Field(alias="resourceType")
    id: str | None = None
    name: str | None = None
    version: int | None = None
    dirty: bool | None = None
    published: bool | None = None
    change_kind: str | None = Field(default=None, alias="changeKind")


class LibraryResourcesResult(FlexibleView):
    library_id: str = Field(alias="libraryId")
    resource_type: str = Field(alias="resourceType")
    items: list[LibraryResourceRow] | None = None
    resources: dict[str, list[LibraryResourceRow]] | None = None
    pagination: Pagination | None = None
    total_count: int | None = Field(default=None, alias="totalCount")


class DevelopmentLibraryReviewResult(FlexibleView):
    resource_type: str | None = Field(default=None, alias="resourceType")
    depth: str | None = None
    library: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    id_usage: dict[str, Any] | None = Field(default=None, alias="idUsage")
    changes: dict[str, Any] | None = None
    narrative: str | None = None


class PropertyActivityResult(FlexibleView):
    resource_type: str | None = Field(default=None, alias="resourceType")
    property_id: str | None = Field(default=None, alias="propertyId")
    window: dict[str, Any] | None = None
    focus: str | None = None
    deployments: dict[str, Any] | None = None
    edits: dict[str, Any] | None = None
    narrative: str | None = None
    id_usage: dict[str, Any] | None = Field(default=None, alias="idUsage")


class SessionState(FlexibleView):
    active_property_id: str | None = Field(default=None, alias="activePropertyId")
    active_property_name: str | None = Field(default=None, alias="activePropertyName")
    active_library_id: str | None = Field(default=None, alias="activeLibraryId")
    active_library_name: str | None = Field(default=None, alias="activeLibraryName")
