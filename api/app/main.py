from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.adobe.reactor_client import ReadOnlyReactorClient
from app.auth.factory import create_auth_provider
from app.auth.session_store import SessionStore
from app.common.responses import error_response
from app.config import Settings, load_settings
from app.middleware.authenticate import AuthenticateMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.routes.activity import router as activity_router
from app.routes.analysis import router as analysis_router
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.libraries import router as libraries_router
from app.routes.session import router as session_router
from app.routes.system import router as system_router
from app.routes.tags import router as tags_router
from app.services.activity import ActivityService
from app.services.analysis import AnalysisService
from app.services.libraries import LibrariesService
from app.services.revisions import RevisionService
from app.services.session_manager import SessionManager
from app.services.tags import TagsService
from app.services.usage import UsageService


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or load_settings()
    session_store = SessionStore(app_settings.data_dir / "session.json", app_settings.vault_key)
    auth_provider = create_auth_provider(app_settings, session_store)
    session_manager = SessionManager(session_store)
    reactor = ReadOnlyReactorClient(auth_provider, app_settings.reactor_base_url)
    revision_service = RevisionService(reactor, max_revision_pages=10)
    tags_service = TagsService(
        reactor,
        default_page_size=app_settings.default_page_size,
        max_page_size=app_settings.max_page_size,
        revision_service=revision_service,
    )
    libraries_service = LibrariesService(
        reactor,
        default_page_size=app_settings.default_page_size,
        max_page_size=app_settings.max_page_size,
        revision_service=revision_service,
    )
    analysis_service = AnalysisService(reactor, max_scan_pages=20, revision_service=revision_service)
    activity_service = ActivityService(reactor)
    usage_service = UsageService(reactor, revision_service=revision_service)

    app = FastAPI(
        title="Adobe Tags API",
        version=app_settings.api_version,
        docs_url="/docs" if app_settings.environment == "development" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.auth_provider = auth_provider
    app.state.session_manager = session_manager
    app.state.tags_service = tags_service
    app.state.libraries_service = libraries_service
    app.state.analysis_service = analysis_service
    app.state.activity_service = activity_service
    app.state.usage_service = usage_service
    app.state.revision_service = revision_service

    app.add_middleware(AuthenticateMiddleware, settings=app_settings)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router)
    app.include_router(system_router)
    app.include_router(auth_router)
    app.include_router(session_router)
    app.include_router(tags_router)
    app.include_router(libraries_router)
    app.include_router(analysis_router)
    app.include_router(activity_router)

    @app.exception_handler(404)
    async def not_found_handler(request: Request, _exc):
        request_id = getattr(request.state, "request_id", None)
        return error_response(
            status_code=404,
            code="NOT_FOUND",
            message="The requested resource was not found.",
            request_id=request_id,
        )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    main()
