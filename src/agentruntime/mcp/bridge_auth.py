"""Bridge outbound auth/header mapping — mirror agentruntime-mcp-go bridge_auth.go."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, MutableMapping, Optional


def _string_from_map(m: Optional[Mapping[str, Any]], key: str) -> str:
    if not m:
        return ""
    v = m.get(key)
    if v is None:
        return ""
    return v if isinstance(v, str) else str(v)


def _config_string(cfg: Optional[Mapping[str, Any]], key: str) -> str:
    if not cfg or not key:
        return ""
    v = cfg.get(key)
    if v is None:
        return ""
    return v.strip() if isinstance(v, str) else str(v).strip()


def apply_auth_mapping(
    cfg: Mapping[str, Any],
    mapping: Optional[Mapping[str, Any]],
) -> Dict[str, str]:
    """auth_mapping: { type: none | bearer | header, from?, name? }."""
    h: Dict[str, str] = {}
    if not mapping:
        return h

    typ = _string_from_map(mapping, "type").lower().strip()
    if not typ or typ == "none":
        return h

    from_key = _string_from_map(mapping, "from").strip()
    if not from_key:
        from_key = _string_from_map(mapping, "value_from").strip()
    val = _config_string(cfg, from_key)
    if not val and typ != "none":
        raise ValueError(f'auth mapping requires config key "{from_key}"')

    if typ == "bearer":
        h["Authorization"] = f"Bearer {val}"
    elif typ == "header":
        name = _string_from_map(mapping, "name").strip()
        if not name:
            raise ValueError("auth mapping type header requires name")
        h[name] = val
    else:
        raise ValueError(f'unsupported auth_mapping type "{typ}"')
    return h


def apply_header_mappings(
    cfg: Mapping[str, Any],
    mappings: List[Optional[Mapping[str, Any]]],
) -> Dict[str, str]:
    """Each mapping: { name, from } or { name, value_from }."""
    h: Dict[str, str] = {}
    for m in mappings:
        if not m:
            continue
        name = _string_from_map(m, "name").strip()
        from_key = _string_from_map(m, "from").strip()
        if not from_key:
            from_key = _string_from_map(m, "value_from").strip()
        if not name:
            raise ValueError("header mapping requires name")
        if not from_key:
            raise ValueError(f'header mapping for "{name}" requires from')
        val = _config_string(cfg, from_key)
        if not val:
            raise ValueError(f'header mapping requires config key "{from_key}"')
        h[name] = val
    return h


def _coerce_header_mappings(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
    return out


def apply_bridge_headers(
    cfg: Mapping[str, Any],
    bridge: Optional[Mapping[str, Any]],
) -> Dict[str, str]:
    """Merge auth_mapping then header_mappings from bridge metadata."""
    h: Dict[str, str] = {}
    if not bridge:
        return h

    auth_map = bridge.get("auth_mapping")
    if isinstance(auth_map, dict):
        h.update(apply_auth_mapping(cfg, auth_map))

    header_mappings = _coerce_header_mappings(bridge.get("header_mappings"))
    if not header_mappings:
        return h
    h.update(apply_header_mappings(cfg, header_mappings))
    return h
