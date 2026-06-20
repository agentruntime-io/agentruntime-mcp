"""Generic MCP bridge route — mirror agentruntime-mcp-go bridge.go."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Mapping, Optional

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response

from .auth_http import extract_token_from_headers, is_schema_endpoint_for_mount
from .bridge_auth import apply_bridge_headers
from .control import build_runtime_context_from_request, fetch_control_payload
from .errors import ControlError, human_message_from_control_api_body

BRIDGE_MOUNT_PATH = "/bridge/mcp"
_LOG = logging.getLogger(__name__)


def _bridge_control_err(err: BaseException) -> str:
    if isinstance(err, ControlError):
        hm = human_message_from_control_api_body(err.body)
        if hm:
            return hm
    return str(err)


def _bridge_upstream_from_payload(bridge: Optional[Mapping[str, Any]]) -> str:
    if not bridge:
        raise ValueError(
            "server is not configured for bridge mode (missing metadata.bridge upstream_url)"
        )
    upstream = str(bridge.get("upstream_url", "")).strip()
    if not upstream:
        raise ValueError("bridge upstream_url is not set on mcp_servers.metadata")
    return upstream


def _tool_name_from_params(data: Mapping[str, Any]) -> Optional[str]:
    params = data.get("params")
    if not isinstance(params, dict):
        return None
    name = str(params.get("name", "")).strip()
    return name or None


def _json_rpc_response(
    req_id: Any,
    result: Optional[Dict[str, Any]] = None,
    rpc_err: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    body: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
    if rpc_err is not None:
        body["error"] = rpc_err
    else:
        body["result"] = result or {}
    return JSONResponse(body)


def _json_rpc_err(code: int, message: str) -> Dict[str, Any]:
    return {"code": code, "message": message}


async def _bridge_post(
    target_url: str,
    payload: Mapping[str, Any],
    extra_headers: Mapping[str, str],
) -> Dict[str, Any]:
    if not target_url.strip():
        raise ValueError("proxy target not configured")
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        **dict(extra_headers),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(target_url, json=dict(payload), headers=headers)
    if resp.status_code != 200:
        raise ValueError(f"proxy target not configured: target returned {resp.status_code}: {resp.text}")
    try:
        parsed = resp.json()
    except Exception as exc:
        raise ValueError(f"proxy target not configured: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("proxy target not configured: invalid JSON object")
    return parsed


async def bridge_http_endpoint(request: Request) -> Response:
    mount = BRIDGE_MOUNT_PATH
    path = request.url.path

    if is_schema_endpoint_for_mount(request.method, path, mount):
        token = extract_token_from_headers(request.headers)
        ctx = build_runtime_context_from_request(request)
        try:
            payload = fetch_control_payload(token, {}, ctx)
            return JSONResponse(payload.config_schema or {})
        except Exception as err:
            return PlainTextResponse(_bridge_control_err(err), status_code=502)

    if request.method.upper() != "POST":
        return PlainTextResponse("Method Not Allowed", status_code=405)

    try:
        data = await request.json()
    except Exception:
        return _json_rpc_response(None, rpc_err=_json_rpc_err(-32700, "Parse error"))
    if not isinstance(data, dict):
        return _json_rpc_response(None, rpc_err=_json_rpc_err(-32700, "Parse error"))

    req_id = data.get("id")
    method = data.get("method") if isinstance(data.get("method"), str) else ""

    ctx = build_runtime_context_from_request(request)
    if method == "tools/call":
        tn = _tool_name_from_params(data)
        if tn:
            ctx["tool_name"] = tn

    token = extract_token_from_headers(request.headers)
    try:
        control_payload = fetch_control_payload(token, {}, ctx)
    except Exception as err:
        return _json_rpc_response(req_id, rpc_err=_json_rpc_err(-32603, _bridge_control_err(err)))

    try:
        upstream = _bridge_upstream_from_payload(control_payload.bridge)
    except Exception as err:
        return _json_rpc_response(req_id, rpc_err=_json_rpc_err(-32603, str(err)))

    try:
        auth_hdr = apply_bridge_headers(control_payload.config, control_payload.bridge)
    except Exception as err:
        return _json_rpc_response(req_id, rpc_err=_json_rpc_err(-32603, f"upstream auth: {err}"))

    try:
        proxied = await _bridge_post(upstream, data, auth_hdr)
    except Exception as err:
        return _json_rpc_response(req_id, rpc_err=_json_rpc_err(-32603, str(err)))

    if method in ("tools/list", "tools/call"):
        result = proxied.get("result")
        if not isinstance(result, dict):
            result = {}
        return _json_rpc_response(req_id, result=result)
    return JSONResponse(proxied)


def bridge_routes() -> list[Any]:
    """Starlette routes for the generic bridge mount."""
    from starlette.routing import Route

    return [
        Route(BRIDGE_MOUNT_PATH, endpoint=bridge_http_endpoint, methods=["GET", "POST"]),
        Route(f"{BRIDGE_MOUNT_PATH}/", endpoint=bridge_http_endpoint, methods=["GET", "POST"]),
        Route(
            f"{BRIDGE_MOUNT_PATH}/config/schema",
            endpoint=bridge_http_endpoint,
            methods=["GET"],
        ),
    ]
