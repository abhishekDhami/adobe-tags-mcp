from __future__ import annotations

from pydantic import Field

from .tags import FlexibleView


class RuleDependenciesResult(FlexibleView):
    resource_type: str | None = Field(default=None, alias="resourceType")
    narrative: str | None = None


class UsageSearchResult(FlexibleView):
    resource_type: str | None = Field(default=None, alias="resourceType")
    property_id: str | None = Field(default=None, alias="propertyId")
    query: str | None = None
    version_scope: str | None = Field(default=None, alias="versionScope")
    status: str | None = None
    narrative: str | None = None
