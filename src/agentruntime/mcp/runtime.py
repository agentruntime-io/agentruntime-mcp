from __future__ import annotations

import os
import yaml
from typing import Any, Dict
from fastmcp import FastMCP
from starlette.responses import JSONResponse

from .decorators import mount_tools
from .schemas import build_schemas
from .middleware import (
    CustomHeaderMiddleware,
    AuthTokenMiddleware,
    HMACAuthMiddleware,
    ControlConfigMiddleware,
    DebugInitMiddleware,
    InitParamsCompatMiddleware,
    _patch_middleware_session_for_stateless_request_context,
)


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def make_server(config_path: str = "config.yaml") -> FastMCP:
    _patch_middleware_session_for_stateless_request_context()
    cfg = load_config(config_path)
    name = cfg.get("server", {}).get("name", "MCPServer")
    app = FastMCP(name=name)
    config_schema = cfg.get("config", {}) or {}

    # Middleware toggles (order: last added = first to run)
    app.add_middleware(InitParamsCompatMiddleware())
    if os.getenv("MCP_DEBUG_INITIALIZE", "").strip() in ("1", "true", "yes"):
        app.add_middleware(DebugInitMiddleware())
    if cfg.get("tracing", {}).get("enabled", True):
        app.add_middleware(CustomHeaderMiddleware())
    auth_mode = os.getenv("MCP_AUTH_MODE") or cfg.get("auth", {}).get("mode", "token")
    if auth_mode == "token":
        app.add_middleware(AuthTokenMiddleware())
    elif auth_mode == "hmac":
        app.add_middleware(HMACAuthMiddleware())
    app.add_middleware(ControlConfigMiddleware(config_schema=config_schema))

    # Mount tools from decorators registry; add list_tools
    mount_tools(app, build_schemas)

    # Schema endpoint for Control connectivity check: GET /mcp/config/schema
    @app.custom_route(path="/mcp/config/schema", methods=["GET"])
    async def _schema_endpoint(request: Any) -> Any:
        return JSONResponse(config_schema or {})

    return app


def run(config_path: str = "config.yaml") -> None:
    app = make_server(config_path)
    cfg = load_config(config_path)
    host = os.getenv("HOST") or cfg.get("server", {}).get("host", "127.0.0.1")
    port = int(os.getenv("PORT") or cfg.get("server", {}).get("port", 8000))
    stateless = cfg.get("server", {}).get("stateless_http", True)
    # json_response=True: return application/json instead of SSE for tools/list etc.
    # Required for Control discover and other clients that expect plain JSON.
    app.run(transport="http", host=host, port=port, stateless_http=stateless, json_response=True)


