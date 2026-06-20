"""Control POST /mcp/config client — mirror agentruntime-mcp-go control.go."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

from .errors import ControlError

HEADER_MCP_INSTANCE_ID = "X-MCP-Instance-Id"
HEADER_MCP_SERVER_ID = "X-MCP-Server-Id"


@dataclass
class ControlPayload:
    config: Dict[str, Any] = field(default_factory=dict)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    bridge: Optional[Dict[str, Any]] = None


def fetch_control_payload(
    token: str,
    config_schema: Mapping[str, Any],
    runtime_context: Mapping[str, Any],
) -> ControlPayload:
    base = os.environ.get("MCP_CONTROL_SERVER_URL", "").strip().rstrip("/")
    if not base:
        return ControlPayload()

    timeout = 5.0
    ts = os.environ.get("MCP_CONTROL_TIMEOUT_SEC", "").strip()
    if ts:
        try:
            n = int(ts)
            if n > 0:
                timeout = float(n)
        except ValueError:
            pass

    payload = {
        "configSchema": dict(config_schema),
        "config_schema": dict(config_schema),
        "schema": dict(config_schema),
        "runtimeContext": dict(runtime_context),
        "runtime_context": dict(runtime_context),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        f"{base}/mcp/config",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urlerror.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""
        raise ControlError(exc.code, body) from exc
    except Exception as exc:
        raise ControlError(502, str(exc)) from exc

    if not raw:
        return ControlPayload()
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise ControlError(502, f"invalid response: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ControlError(502, "invalid control config response")

    out = ControlPayload()
    cfg = parsed.get("config")
    if isinstance(cfg, dict):
        out.config = cfg
    cs = parsed.get("config_schema")
    if isinstance(cs, dict):
        out.config_schema = cs
    bridge = parsed.get("bridge")
    if isinstance(bridge, dict):
        out.bridge = bridge
    return out


def build_runtime_context_from_request(req: Any) -> Dict[str, Any]:
    """Build runtime_context for bridge/control calls from a Starlette request."""
    ctx: Dict[str, Any] = {}
    if req is None:
        ctx["tool_name"] = "__initialize"
        return ctx

    headers = getattr(req, "headers", None)

    def _hdr(name: str) -> str:
        if headers is None:
            return ""
        v = headers.get(name)
        return v.strip() if isinstance(v, str) else ""

    inst = _hdr(HEADER_MCP_INSTANCE_ID) or _hdr("x-mcp-instance-id")
    if inst:
        ctx["instance_id"] = inst

    sid = _hdr(HEADER_MCP_SERVER_ID) or _hdr("x-mcp-server-id")
    env_sid = os.environ.get("MCP_SERVER_ID", "").strip()
    if env_sid:
        sid = env_sid
    if sid:
        ctx["server_id"] = sid

    tn = _hdr("X-Tool-Name") or _hdr("x-tool-name") or _hdr("X-MCP-Tool-Name") or _hdr("x-mcp-tool-name")
    ctx["tool_name"] = tn or "__initialize"
    return ctx
