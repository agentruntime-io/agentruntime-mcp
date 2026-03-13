from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
import httpx
from starlette.responses import JSONResponse
import yaml

from .middleware import _patch_middleware_session_for_stateless_request_context, _request_from_context


def _overlay(overlay_file: Optional[str]) -> Dict[str, Any]:
    if not overlay_file:
        return {}
    try:
        with open(overlay_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _post(target_url: str, payload: Dict[str, Any], bearer_token: Optional[str]) -> Dict[str, Any]:
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    r = httpx.post(target_url, headers=headers, content=json.dumps(payload), timeout=15)
    r.raise_for_status()
    return r.json()


def _fetch_and_merge_tools(
    target_url: str, overlay_file: Optional[str], bearer_token: Optional[str]
) -> List[Dict[str, Any]]:
    """Fetch tools from target and merge with overlay. Returns merged tools list."""
    if not target_url:
        return []
    res = _post(target_url, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, bearer_token)
    tools: List[Dict[str, Any]] = res.get("result", {}).get("tools", [])
    ov = _overlay(overlay_file)
    ov_map = {t.get("name"): t for t in ov.get("tools", [])}
    merged: List[Dict[str, Any]] = []
    for t in tools:
        name = t.get("name")
        if name in ov_map:
            mt = {**t}
            o = ov_map[name]
            if o.get("description"):
                mt["description"] = o["description"]
            if o.get("inputSchema"):
                mt["inputSchema"] = o["inputSchema"]
            if o.get("outputSchema"):
                mt["outputSchema"] = o["outputSchema"]
            merged.append(mt)
        else:
            merged.append(t)
    return merged


class ProxyToolsListMiddleware(Middleware):
    """Intercepts tools/list and returns target's tools (merged with overlay) directly."""

    def __init__(self, target_url: str, overlay_file: Optional[str], bearer_token: Optional[str]) -> None:
        self.target_url = target_url
        self.overlay_file = overlay_file
        self.bearer_token = bearer_token

    async def on_request(self, context: MiddlewareContext, call_next: Any) -> Any:
        req = _request_from_context(context)
        if req is None:
            return await call_next(context)
        try:
            body = await req.body()
            if not body:
                return await call_next(context)
            data = json.loads(body)
            if data.get("method") != "tools/list":
                object.__setattr__(req, "_body", body)
                return await call_next(context)
            merged = await asyncio.to_thread(
                _fetch_and_merge_tools, self.target_url, self.overlay_file, self.bearer_token
            )
            return JSONResponse({"jsonrpc": "2.0", "id": data.get("id"), "result": {"tools": merged}})
        except Exception:
            return await call_next(context)


class ProxyToolsCallMiddleware(Middleware):
    """Intercepts tools/call and forwards to target."""

    def __init__(self, target_url: str, bearer_token: Optional[str]) -> None:
        self.target_url = target_url
        self.bearer_token = bearer_token

    async def on_request(self, context: MiddlewareContext, call_next: Any) -> Any:
        req = _request_from_context(context)
        if req is None:
            return await call_next(context)
        req_id = None
        try:
            body = await req.body()
            if not body:
                return await call_next(context)
            data = json.loads(body)
            req_id = data.get("id")
            if data.get("method") != "tools/call":
                object.__setattr__(req, "_body", body)
                return await call_next(context)
            params = data.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments")
            if arguments is None:
                arguments = {}
            if not self.target_url:
                return JSONResponse(
                    {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32600, "message": "Proxy target not configured"}}
                )
            res = await asyncio.to_thread(
                _post,
                self.target_url,
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
                self.bearer_token,
            )
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": res.get("result", {})})
        except httpx.HTTPStatusError as e:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(e)}},
                status_code=e.response.status_code,
            )
        except Exception as e:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(e)}}
            )


def build_proxy_app(target_url: str, overlay_file: Optional[str] = None, bearer_token: Optional[str] = None) -> FastMCP:
    app = FastMCP(name="MCPProxy")
    app.add_middleware(ProxyToolsListMiddleware(target_url, overlay_file, bearer_token))
    app.add_middleware(ProxyToolsCallMiddleware(target_url, bearer_token))
    return app


def run_proxy(
    target_url: str,
    overlay_file: Optional[str] = None,
    bearer_token: Optional[str] = None,
    host: str = "127.0.0.1",
    port: int = 8010,
) -> None:
    _patch_middleware_session_for_stateless_request_context()
    app = build_proxy_app(target_url, overlay_file, bearer_token)
    app.run(transport="http", host=host, port=port, stateless_http=True)
