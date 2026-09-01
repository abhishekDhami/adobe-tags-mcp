from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import StrictModel


ViewDepth = Literal["index", "detail", "context", "full"]


class FlexibleView(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Pagination(StrictModel):
    page: int
    page_size: int = Field(alias="pageSize")
    total_items: int = Field(alias="totalItems")
    total_pages: int = Field(alias="totalPages")
    has_next_page: bool | None = Field(default=None, alias="hasNextPage")
    has_previous_page: bool | None = Field(default=None, alias="hasPreviousPage")


class ViewMeta(FlexibleView):
    depth: str
    resource_type: str = Field(alias="resourceType")
    code_included: bool = Field(alias="codeIncluded")
    truncated: bool = False


class ResourceSummary(FlexibleView):
    resource_type: str | None = Field(default=None, alias="resourceType")
    id: str | None = None
    name: str | None = None
    enabled: bool | None = None
    dirty: bool | None = None
    meta: ViewMeta | None = None


class RuleSummary(ResourceSummary):
    pass


class PaginatedResources(StrictModel):
    items: list[ResourceSummary]
    pagination: Pagination


class PaginatedRules(StrictModel):
    items: list[RuleSummary]
    pagination: Pagination


class RuleLogicBlock(FlexibleView):
    events: list[dict[str, Any]] = Field(default_factory=list)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    unknown: list[dict[str, Any]] | None = None


class RuleDetail(FlexibleView):
    resource_type: str = Field(alias="resourceType")
    id: str | None = None
    name: str | None = None
    enabled: bool | None = None
    dirty: bool | None = None
    version: int | None = None
    published: bool | None = None
    published_at: str | None = Field(default=None, alias="publishedAt")
    review_status: str | None = Field(default=None, alias="reviewStatus")
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")
    property: dict[str, Any] | None = None
    logic: RuleLogicBlock | None = None
    references: dict[str, Any] | None = None
    meta: ViewMeta | None = None


class ResourceDetail(FlexibleView):
    resource_type: str = Field(alias="resourceType")
    id: str | None = None
    name: str | None = None
    enabled: bool | None = None
    version: int | None = None
    installed_extension_version: str | None = Field(default=None, alias="installedExtensionVersion")
    meta: ViewMeta | None = None


class RevisionHistoryResult(FlexibleView):
    resource_type: str | None = Field(default=None, alias="resourceType")
    resource_kind: str | None = Field(default=None, alias="resourceKind")
    head_id: str | None = Field(default=None, alias="headId")
    name: str | None = None
    view: str | None = None
    revisions: list[dict[str, Any]] | None = None
    total_count: int | None = Field(default=None, alias="totalCount")
    important_count: int | None = Field(default=None, alias="importantCount")
    full_revision_count: int | None = Field(default=None, alias="fullRevisionCount")


class AuthStatusResult(StrictModel):
    connected: bool
    mode: str | None = None
    org_id: str | None = Field(default=None, alias="orgId")
    user_email: str | None = Field(default=None, alias="userEmail")
    message: str
