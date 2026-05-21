"""HTTP helpers mirroring agentruntime-mcp-go auth.go."""

from __future__ import annotations

from typing import Any, Mapping, Optional
import urllib.parse

NO_CONFIG_METHODS = frozenset({"tools/list", "initialize", "notifications/initialized"})


def extract_token_from_headers(headers: Mapping[str, Any]) -> str:
    auth = headers.get("authorization") or headers.get("Authorization")
    if isinstance(auth, str) and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    xt = headers.get("x-mcp-token") or headers.get("X-MCP-Token")
    if isinstance(xt, str) and xt.strip():
        return xt.strip()
    return ""


def normalize_url_path(url_path: str) -> str:
    p = urllib.parse.urlsplit(url_path).path or ""
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p or "/"


def is_schema_endpoint_for_mount(method: str, url_path: str, mount_path: str) -> bool:
    if method.upper() != "GET":
        return False
    path = normalize_url_path(url_path)
    mp = mount_path.rstrip("/") or "/"
    schema_path = normalize_url_path(mp + "/config/schema")
    return path == schema_path


def needs_resolved_config_from_body(data: Optional[Mapping[str, Any]]) -> bool:
    if not data or not isinstance(data, Mapping):
        return True
    m = data.get("method")
    if not isinstance(m, str):
        return True
    return m not in NO_CONFIG_METHODS
