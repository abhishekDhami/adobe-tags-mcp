from __future__ import annotations

import argparse
import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import replace

import anyio
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.clients import ApiClient
from app.config import Settings, load_settings, validate_runtime_settings
from app.context import AppContext
from app.logging_config import configure_logging
from app.tools import register_analysis_tools, register_library_tools, register_system_tools, register_tags_tools


class RequestBodyTooLargeError(RuntimeError):
    """Raised internally when an HTTP request exceeds the configured byte limit."""


class RequestBodyLimitMiddleware:
    """Reject oversized HTTP request bodies before MCP message processing."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = 0
            if declared_size > self.max_bytes:
                await self._send_rejection(scope, receive, send)
                return

        received_bytes = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_bytes:
                    raise RequestBodyTooLargeError
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyTooLargeError:
            if not response_started:
                await self._send_rejection(scope, receive, send)

    @staticmethod
    async def _send_rejection(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            {"error": "request_body_too_large"},
            status_code=413,
        )
        await response(scope, receive, send)


def create_server(
    settings: Settings,
    logger: logging.Logger | None = None,
) -> FastMCP[AppContext]:
    """Build one MCP server whose business tools work with either transport."""
    validate_runtime_settings(settings)
    app_logger = logger or configure_logging(settings.log_level)

    @asynccontextmanager
    async def app_lifespan(_server: FastMCP[AppContext]) -> AsyncIterator[AppContext]:
        client = ApiClient(settings=settings, logger=app_logger)
        app_logger.info("MCP server dependencies initialized")
        try:
            yield AppContext(api=client)
        finally:
            await client.close()
            app_logger.info("MCP server dependencies closed")

    server = FastMCP(
        settings.server_name,
        lifespan=app_lifespan,
        log_level=settings.log_level,
        host=settings.mcp_http_host,
        port=settings.mcp_http_port,
        streamable_http_path=settings.mcp_http_path,
        stateless_http=settings.mcp_http_stateless,
        json_response=settings.mcp_http_json_response,
    )

    @server.custom_route(settings.mcp_http_health_path, methods=["GET"])
    async def health_check(_request: Request) -> Response:
        """Process-level health endpoint available in Streamable HTTP mode."""
        return JSONResponse(
            {
                "status": "ok",
                "service": settings.server_name,
                "transport": "streamable-http",
                "mcpEndpoint": settings.mcp_http_path,
            }
        )

    register_system_tools(server)
    register_tags_tools(server)
    register_library_tools(server)
    register_analysis_tools(server)
    return server


def create_http_app(server: FastMCP[AppContext], settings: Settings) -> ASGIApp:
    """Create the Streamable HTTP ASGI app with starter-level protections."""
    return RequestBodyLimitMiddleware(
        server.streamable_http_app(),
        max_bytes=settings.mcp_http_max_request_body_bytes,
    )


async def _serve_streamable_http(
    server: FastMCP[AppContext], settings: Settings
) -> None:
    app = create_http_app(server, settings)
    config = uvicorn.Config(
        app,
        host=settings.mcp_http_host,
        port=settings.mcp_http_port,
        log_level=settings.log_level.lower(),
    )
    await uvicorn.Server(config).serve()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Adobe Tags MCP adapter.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        help="Override MCP_TRANSPORT for this process.",
    )
    return parser.parse_args(argv)


def run(settings: Settings) -> None:
    """Run the configured MCP transport."""
    validate_runtime_settings(settings)
    logger = configure_logging(settings.log_level)
    server = create_server(settings, logger=logger)

    if settings.mcp_transport == "stdio":
        logger.info("Starting MCP server with stdio transport")
        server.run(transport="stdio")
        return

    logger.info(
        "Starting MCP server with Streamable HTTP transport at %s; health=%s; "
        "stateless=%s; json_response=%s; max_request_body_bytes=%s",
        settings.mcp_http_url,
        settings.mcp_http_health_url,
        settings.mcp_http_stateless,
        settings.mcp_http_json_response,
        settings.mcp_http_max_request_body_bytes,
    )
    anyio.run(_serve_streamable_http, server, settings)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = load_settings()
    if args.transport:
        settings = replace(settings, mcp_transport=args.transport)
    run(settings)


if __name__ == "__main__":
    main()
