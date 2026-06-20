from __future__ import annotations

import os
from contextlib import AsyncExitStack, asynccontextmanager
import yaml
from typing import Any, Dict, List

from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from .decorators import mount_tools
from .schemas import build_schemas
from .middleware import (
    CustomHeaderMiddleware,
    ControlConfigMiddleware,
    DebugInitMiddleware,
    InitParamsCompatMiddleware,
    _patch_middleware_session_for_stateless_request_context,
)
from .config_schema import SchemaWriter
from .errors import ErrAdapterNotFound

_WEBHOOK_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def make_server(config_path: str = "config.yaml") -> FastMCP:
    """Single MCP server at /mcp using declarative tools + Control middleware (Go-parity defaults)."""
    _patch_middleware_session_for_stateless_request_context()
    cfg = load_config(config_path)
    name = cfg.get("server", {}).get("name", "MCPServer")
    app = FastMCP(name=name)
    config_schema = dict(cfg.get("config") or {})

    app.add_middleware(InitParamsCompatMiddleware())
    if os.getenv("MCP_DEBUG_INITIALIZE", "").strip() in ("1", "true", "yes"):
        app.add_middleware(DebugInitMiddleware())
    if cfg.get("tracing", {}).get("enabled", True):
        app.add_middleware(CustomHeaderMiddleware())

    app.add_middleware(ControlConfigMiddleware(config_schema=config_schema, mount_path="/mcp"))

    mount_tools(app, build_schemas)

    return app


def _apply_http_middleware(
    app: FastMCP,
    cfg: Dict[str, Any],
    schema_map: Dict[str, Any],
    *,
    mount_path: str = "/mcp",
) -> None:
    """Shared Control + tracing stack (same order as :func:`run_with_registry`)."""
    app.add_middleware(InitParamsCompatMiddleware())
    if os.getenv("MCP_DEBUG_INITIALIZE", "").strip() in ("1", "true", "yes"):
        app.add_middleware(DebugInitMiddleware())
    if cfg.get("tracing", {}).get("enabled", True):
        app.add_middleware(CustomHeaderMiddleware())
    app.add_middleware(ControlConfigMiddleware(config_schema=schema_map, mount_path=mount_path))


def _adapter_http_app(
    adapter_name: str, cfg: Dict[str, Any], schema_map: Dict[str, Any], sw: SchemaWriter
) -> Any:
    """One FastMCP + streamable HTTP Starlette app; mounted under ``/{adapter_name}`` so the MCP path is ``/{adapter}/mcp``."""
    from .adapter_registry import instantiate_adapters

    base_name = cfg.get("server", {}).get("name", "MCPServer")
    app = FastMCP(name=f"{base_name}-{adapter_name}")
    for ad in instantiate_adapters([adapter_name]):
        ad.register(app, sw)
    _apply_http_middleware(app, cfg, schema_map, mount_path="/mcp")
    stateless = cfg.get("server", {}).get("stateless_http", True)
    return app.http_app(
        path="/mcp",
        json_response=True,
        stateless_http=stateless,
        transport="http",
    )


def run(config_path: str = "config.yaml") -> None:
    app = make_server(config_path)
    cfg = load_config(config_path)
    host = os.getenv("HOST") or cfg.get("server", {}).get("host", "127.0.0.1")
    port = int(os.getenv("PORT") or cfg.get("server", {}).get("port", 8000))
    stateless = cfg.get("server", {}).get("stateless_http", True)
    app.run(transport="http", host=host, port=port, stateless_http=stateless, json_response=True)


def run_with_registry(config_path: str = "config.yaml", *adapter_names: str) -> None:
    """Plugin-style adapters registered via adapter_registry.register_adapter."""
    _patch_middleware_session_for_stateless_request_context()
    cfg = load_config(config_path)
    name = cfg.get("server", {}).get("name", "MCPServer")
    app = FastMCP(name=name)
    schema_map = dict(cfg.get("config") or {})
    sw = SchemaWriter(schema_map)

    from .adapter_registry import instantiate_adapters, list_adapter_names

    names = list(adapter_names) if adapter_names else list_adapter_names()
    for ad in instantiate_adapters(names):
        ad.register(app, sw)

    _apply_http_middleware(app, cfg, schema_map, mount_path="/mcp")

    host = os.getenv("HOST") or cfg.get("server", {}).get("host", "127.0.0.1")
    port = int(os.getenv("PORT") or cfg.get("server", {}).get("port", 8000))
    stateless = cfg.get("server", {}).get("stateless_http", True)
    app.run(transport="http", host=host, port=port, stateless_http=stateless, json_response=True)


def run_with_router(config_path: str = "config.yaml") -> None:
    """HTTP router parity with Go ``RunWithRouter`` / TS ``runWithRouter``.

    - MCP streamable HTTP at ``/{adapter_name}/mcp`` for each entry in ``register_adapter``.
    - Optional ``WebhookAdapter.register_webhook`` routes are registered on the **root** app
      (evaluate before adapter mounts), matching Go/TS dispatch order.
    - Operators expose inbound vendor URLs as ``https://<host>:<port><path>`` for each
      webhook route (same process as MCP).
    """
    _patch_middleware_session_for_stateless_request_context()
    cfg = load_config(config_path)

    from .adapter_registry import ServeMux, instantiate_adapters, list_adapter_names

    names: List[str] = list_adapter_names()
    if not names:
        raise ErrAdapterNotFound("(no adapters registered)")

    schema_map = dict(cfg.get("config") or {})
    sw = SchemaWriter(schema_map)

    mux = ServeMux()
    for n in names:
        for ad in instantiate_adapters([n]):
            reg = getattr(ad, "register_webhook", None)
            if callable(reg):
                reg(mux)

    from .bridge import bridge_routes

    sub_apps: List[Any] = []
    routes: List[Any] = list(bridge_routes())
    for path, handler in mux:
        routes.append(Route(path, endpoint=handler, methods=list(_WEBHOOK_METHODS)))
    for n in names:
        sub = _adapter_http_app(n, cfg, schema_map, sw)
        sub_apps.append(sub)
        routes.append(Mount(f"/{n}", app=sub))

    @asynccontextmanager
    async def composite_lifespan(_app: Starlette):
        async with AsyncExitStack() as stack:
            for sub in sub_apps:
                await stack.enter_async_context(sub.router.lifespan_context(sub))
            yield

    host = os.getenv("HOST") or cfg.get("server", {}).get("host", "127.0.0.1")
    port = int(os.getenv("PORT") or cfg.get("server", {}).get("port", 8000))

    root = Starlette(routes=routes, lifespan=composite_lifespan)

    import uvicorn

    uvicorn.run(root, host=host, port=port)
