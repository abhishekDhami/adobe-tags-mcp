from __future__ import annotations

import asyncio
import logging
from typing import Any, TypeVar
from uuid import uuid4

import httpx
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.models.common import ApiErrorEnvelope, ApiSuccessEnvelope
from app.models.tools import HealthResult, SystemStatusResult

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class ApiError(RuntimeError):
    """Safe, normalized representation of a local API failure."""

    def __init__(self, code: str, message: str, request_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.request_id = request_id


class ApiClient:
    def __init__(self, settings: Settings, logger: logging.Logger):
        self._settings = settings
        self._logger = logger
        headers = {"Accept": "application/json", "User-Agent": "adobe-tags-mcp/1.0"}
        if settings.auth_enabled:
            headers["Authorization"] = f"Bearer {settings.api_key}"

        self._client = httpx.AsyncClient(
            base_url=settings.api_base_url,
            timeout=httpx.Timeout(settings.api_timeout_seconds),
            headers=headers,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        response_model: type[ResponseModel],
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> ResponseModel:
        request_id = str(uuid4())
        last_transport_error: httpx.HTTPError | None = None

        retry_limit = self._settings.api_max_retries if method.upper() == "GET" else 0

        for attempt in range(retry_limit + 1):
            try:
                response = await self._client.request(
                    method,
                    path,
                    params=params,
                    json=json,
                    headers={"X-Request-ID": request_id},
                )
                return self._parse_response(response, response_model)
            except httpx.TransportError as exc:
                last_transport_error = exc
                if attempt >= retry_limit:
                    break
                await asyncio.sleep(min(0.25 * (2**attempt), 1.0))

        self._logger.error(
            "Local API request failed after retries: %s",
            last_transport_error,
            extra={"request_id": request_id},
        )
        raise ApiError(
            code="API_UNAVAILABLE",
            message="The local API is unavailable. Confirm that it is running and reachable.",
            request_id=request_id,
        )

    def _parse_response(
        self,
        response: httpx.Response,
        response_model: type[ResponseModel],
    ) -> ResponseModel:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError(
                code="INVALID_API_RESPONSE",
                message="The local API returned a non-JSON response.",
                request_id=response.headers.get("x-request-id"),
            ) from exc

        if response.is_error:
            try:
                error_envelope = ApiErrorEnvelope.model_validate(payload)
            except ValidationError:
                raise ApiError(
                    code="API_REQUEST_FAILED",
                    message="The local API rejected the request with an unexpected error response.",
                    request_id=response.headers.get("x-request-id"),
                )
            raise ApiError(
                code=error_envelope.error.code,
                message=error_envelope.error.message,
                request_id=error_envelope.meta.request_id,
            )

        try:
            success_envelope = ApiSuccessEnvelope.model_validate(payload)
            return response_model.model_validate(success_envelope.data)
        except ValidationError as exc:
            self._logger.error(
                "Local API response did not match the MCP contract",
                extra={"request_id": response.headers.get("x-request-id")},
                exc_info=exc,
            )
            raise ApiError(
                code="INVALID_API_RESPONSE",
                message="The local API response did not match the expected contract.",
                request_id=response.headers.get("x-request-id"),
            ) from exc

    async def get_health(self) -> HealthResult:
        return await self._request("GET", "/health", HealthResult)

    async def get_status(self) -> SystemStatusResult:
        return await self._request("GET", "/api/v1/system/status", SystemStatusResult)

    async def get_auth_status(self) -> AuthStatusResult:
        from app.models.tags import AuthStatusResult

        return await self._request("GET", "/api/v1/auth/status", AuthStatusResult)

    async def list_properties(self, *, page: int = 1, page_size: int = 0) -> PaginatedResources:
        from app.models.tags import PaginatedResources

        params: dict[str, Any] = {"page": page}
        if page_size:
            params["pageSize"] = page_size
        return await self._request("GET", "/api/v1/tags/properties", PaginatedResources, params=params)

    async def list_rules(
        self,
        property_id: str,
        *,
        page: int = 1,
        page_size: int = 0,
        search: str | None = None,
    ) -> PaginatedRules:
        from app.models.tags import PaginatedRules

        params: dict[str, Any] = {"page": page}
        if page_size:
            params["pageSize"] = page_size
        if search:
            params["search"] = search
        return await self._request(
            "GET",
            f"/api/v1/tags/properties/{property_id}/rules",
            PaginatedRules,
            params=params,
        )

    async def get_rule(
        self,
        rule_id: str,
        *,
        depth: str = "context",
        include_code: bool = False,
        include_raw_settings: bool = False,
    ) -> RuleDetail:
        from app.models.tags import RuleDetail

        params = {
            "depth": depth,
            "includeCode": str(include_code).lower(),
            "includeRawSettings": str(include_raw_settings).lower(),
        }
        return await self._request("GET", f"/api/v1/tags/rules/{rule_id}", RuleDetail, params=params)

    async def get_rule_versions(
        self,
        rule_id: str,
        *,
        view: str = "important",
    ):
        from app.models.tags import RevisionHistoryResult

        return await self._request(
            "GET",
            f"/api/v1/tags/rules/{rule_id}/versions",
            RevisionHistoryResult,
            params={"view": view},
        )

    async def list_data_elements(
        self,
        property_id: str,
        *,
        page: int = 1,
        page_size: int = 0,
        search: str | None = None,
    ) -> PaginatedResources:
        from app.models.tags import PaginatedResources

        params: dict[str, Any] = {"page": page}
        if page_size:
            params["pageSize"] = page_size
        if search:
            params["search"] = search
        return await self._request(
            "GET",
            f"/api/v1/tags/properties/{property_id}/data-elements",
            PaginatedResources,
            params=params,
        )

    async def get_data_element(
        self,
        data_element_id: str,
        *,
        depth: str = "detail",
        include_code: bool = False,
        include_raw_settings: bool = False,
    ) -> ResourceDetail:
        from app.models.tags import ResourceDetail

        params = {
            "depth": depth,
            "includeCode": str(include_code).lower(),
            "includeRawSettings": str(include_raw_settings).lower(),
        }
        return await self._request(
            "GET",
            f"/api/v1/tags/data-elements/{data_element_id}",
            ResourceDetail,
            params=params,
        )

    async def get_data_element_versions(
        self,
        data_element_id: str,
        *,
        view: str = "important",
    ):
        from app.models.tags import RevisionHistoryResult

        return await self._request(
            "GET",
            f"/api/v1/tags/data-elements/{data_element_id}/versions",
            RevisionHistoryResult,
            params={"view": view},
        )

    async def list_extensions(
        self, property_id: str, *, page: int = 1, page_size: int = 0
    ) -> PaginatedResources:
        from app.models.tags import PaginatedResources

        params: dict[str, Any] = {"page": page}
        if page_size:
            params["pageSize"] = page_size
        return await self._request(
            "GET",
            f"/api/v1/tags/properties/{property_id}/extensions",
            PaginatedResources,
            params=params,
        )

    async def get_extension(
        self,
        extension_id: str,
        *,
        depth: str = "detail",
        include_raw_settings: bool = False,
    ) -> ResourceDetail:
        from app.models.tags import ResourceDetail

        params = {
            "depth": depth,
            "includeRawSettings": str(include_raw_settings).lower(),
        }
        return await self._request(
            "GET", f"/api/v1/tags/extensions/{extension_id}", ResourceDetail, params=params
        )

    async def get_extension_versions(
        self,
        extension_id: str,
        *,
        view: str = "important",
    ):
        from app.models.tags import RevisionHistoryResult

        return await self._request(
            "GET",
            f"/api/v1/tags/extensions/{extension_id}/versions",
            RevisionHistoryResult,
            params={"view": view},
        )

    async def search_tags_resources(
        self,
        query: str,
        *,
        page: int = 1,
        page_size: int = 0,
        resource_types: list[str] | None = None,
    ) -> PaginatedResources:
        from app.models.tags import PaginatedResources

        params: dict[str, Any] = {"query": query, "page": page}
        if page_size:
            params["pageSize"] = page_size
        if resource_types:
            params["resourceTypes"] = resource_types
        return await self._request("GET", "/api/v1/tags/search", PaginatedResources, params=params)

    async def list_environments(self, property_id: str) -> EnvironmentListResult:
        from app.models.libraries import EnvironmentListResult

        return await self._request(
            "GET",
            f"/api/v1/tags/properties/{property_id}/environments",
            EnvironmentListResult,
        )

    async def list_published_libraries(
        self,
        property_id: str,
        *,
        page: int = 1,
        page_size: int = 0,
        state: str = "published",
        environment_id: str | None = None,
        sort: str = "-published_at",
    ) -> PaginatedLibraries:
        from app.models.libraries import PaginatedLibraries

        params: dict[str, Any] = {"page": page, "state": state, "sort": sort}
        if page_size:
            params["pageSize"] = page_size
        if environment_id:
            params["environmentId"] = environment_id
        return await self._request(
            "GET",
            f"/api/v1/tags/properties/{property_id}/published-libraries",
            PaginatedLibraries,
            params=params,
        )

    async def get_development_library(self, property_id: str) -> DevLibraryCandidateResult:
        from app.models.libraries import DevLibraryCandidateResult

        return await self._request(
            "GET",
            f"/api/v1/tags/properties/{property_id}/development-libraries",
            DevLibraryCandidateResult,
        )

    async def get_library(self, library_id: str) -> LibraryDetail:
        from app.models.libraries import LibraryDetail

        return await self._request("GET", f"/api/v1/tags/libraries/{library_id}", LibraryDetail)

    async def list_library_resources(
        self,
        library_id: str,
        *,
        resource_type: str = "all",
        page: int = 1,
        page_size: int = 0,
    ) -> LibraryResourcesResult:
        from app.models.libraries import LibraryResourcesResult

        params: dict[str, Any] = {"resourceType": resource_type, "page": page}
        if page_size:
            params["pageSize"] = page_size
        return await self._request(
            "GET",
            f"/api/v1/tags/libraries/{library_id}/resources",
            LibraryResourcesResult,
            params=params,
        )

    async def review_development_library(
        self,
        library_id: str,
        *,
        depth: str = "summary",
    ):
        from app.models.libraries import DevelopmentLibraryReviewResult

        return await self._request(
            "GET",
            f"/api/v1/tags/libraries/{library_id}/review-development-library",
            DevelopmentLibraryReviewResult,
            params={"depth": depth},
        )

    async def get_property_activity(
        self,
        property_id: str,
        *,
        from_value: str | None = None,
        to_value: str | None = None,
        focus: str = "all",
        prior_deploy_limit: int = 3,
    ):
        from app.models.libraries import PropertyActivityResult

        params: dict[str, Any] = {
            "focus": focus,
            "priorDeployLimit": prior_deploy_limit,
        }
        if from_value:
            params["from"] = from_value
        if to_value:
            params["to"] = to_value
        return await self._request(
            "GET",
            f"/api/v1/tags/properties/{property_id}/activity",
            PropertyActivityResult,
            params=params,
        )

    async def get_rule_dependencies(
        self,
        rule_id: str,
        *,
        version_scope: str = "latest",
    ) -> RuleDependenciesResult:
        from app.models.analysis import RuleDependenciesResult

        params: dict[str, Any] = {"versionScope": version_scope}
        return await self._request(
            "GET",
            f"/api/v1/tags/rules/{rule_id}/dependencies",
            RuleDependenciesResult,
            params=params,
        )

    async def find_usage(
        self,
        property_id: str,
        *,
        query: str,
        version_scope: str = "latest",
        mode: str = "freeText",
        detail: str = "hits",
        library_id: str | None = None,
    ):
        from app.models.analysis import UsageSearchResult

        params: dict[str, Any] = {
            "query": query,
            "versionScope": version_scope,
            "mode": mode,
            "detail": detail,
        }
        if library_id:
            params["libraryId"] = library_id
        return await self._request(
            "GET",
            f"/api/v1/tags/properties/{property_id}/usage",
            UsageSearchResult,
            params=params,
        )

    async def get_session(self) -> SessionState:
        from app.models.libraries import SessionState

        return await self._request("GET", "/api/v1/session", SessionState)

    async def update_session(
        self,
        *,
        active_property_id: str | None = None,
        active_property_name: str | None = None,
        active_library_id: str | None = None,
        active_library_name: str | None = None,
    ) -> SessionState:
        from app.models.libraries import SessionState

        body: dict[str, Any] = {}
        if active_property_id is not None:
            body["activePropertyId"] = active_property_id
        if active_property_name is not None:
            body["activePropertyName"] = active_property_name
        if active_library_id is not None:
            body["activeLibraryId"] = active_library_id
        if active_library_name is not None:
            body["activeLibraryName"] = active_library_name
        return await self._request("PATCH", "/api/v1/session", SessionState, json=body)

    async def clear_session(self) -> dict[str, bool]:
        from pydantic import BaseModel

        class Cleared(BaseModel):
            cleared: bool

        result = await self._request("POST", "/api/v1/session/clear", Cleared)
        return {"cleared": result.cleared}


def to_tool_error(error: ApiError) -> ToolError:
    request_suffix = f" Reference: {error.request_id}." if error.request_id else ""
    return ToolError(f"{error.code}: {error}{request_suffix}")
