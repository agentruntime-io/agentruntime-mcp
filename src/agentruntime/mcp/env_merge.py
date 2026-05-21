"""Env/schema helpers mirroring agentruntime-mcp-go env_config.go."""

from __future__ import annotations

import os
from typing import Any, Dict, Mapping

from .context import ConfigView


def new_lowercase_env_index() -> Dict[str, str]:
    idx: Dict[str, str] = {}
    for name, val in os.environ.items():
        if val is None:
            continue
        v = str(val).strip()
        if not v:
            continue
        idx[name.lower()] = v
    return idx


def lookup_schema_env(idx: Mapping[str, str], schema_key: str) -> str | None:
    k = schema_key.lower()
    if k in idx:
        return idx[k].strip()
    ak = ("AR_" + schema_key).lower()
    if ak in idx:
        return idx[ak].strip()
    return None


def env_overrides_from_schema(schema: Mapping[str, Any], idx: Mapping[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k in schema.keys():
        v = lookup_schema_env(idx, k)
        if v:
            out[k] = v
    return out


def value_as_string(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def required_config_satisfied(schema: Mapping[str, Any], cfg: Mapping[str, Any]) -> bool:
    if not schema:
        return True
    for key, defv in schema.items():
        if not isinstance(defv, dict):
            continue
        meta = defv
        if not meta.get("required"):
            continue
        if value_as_string(cfg.get(key)):
            continue
        if "default" in meta:
            continue
        return False
    return True


def env_alone_satisfies_required(schema: Mapping[str, Any], idx: Mapping[str, str]) -> bool:
    env_only: Dict[str, Any] = {}
    for k in schema.keys():
        v = lookup_schema_env(idx, k)
        if v:
            env_only[k] = v
    return required_config_satisfied(schema, env_only)


def merge_control_with_env_priority(
    control: Mapping[str, Any],
    env_keys: Mapping[str, str],
    schema: Mapping[str, Any],
) -> ConfigView:
    final = ConfigView(dict(control))
    for k in schema.keys():
        if k in env_keys:
            final[k] = env_keys[k]
    return final
