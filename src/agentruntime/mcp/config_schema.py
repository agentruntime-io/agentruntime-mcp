"""Config schema helpers mirroring agentruntime-mcp-go config_schema.go."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional

CONFIG_TYPE_STRING = "string"
CONFIG_TYPE_NUMBER = "number"
CONFIG_TYPE_BOOL = "boolean"


@dataclass
class ConfigField:
    type: str
    display_name: str
    required: bool = False
    default: Any = None


@dataclass
class ConfigFieldDef:
    key: str
    field: ConfigField


ConfigFieldOpt = Callable[[ConfigField], None]


def opt_required() -> ConfigFieldOpt:
    def _apply(f: ConfigField) -> None:
        f.required = True

    return _apply


def opt_default(v: Any) -> ConfigFieldOpt:
    def _apply(f: ConfigField) -> None:
        f.default = v

    return _apply


def field(key: str, typ: str, display_name: str, *opts: ConfigFieldOpt) -> ConfigFieldDef:
    cf = ConfigField(type=typ, display_name=display_name)
    for o in opts:
        o(cf)
    return ConfigFieldDef(key=key, field=cf)


def string_field(key: str, display_name: str, *opts: ConfigFieldOpt) -> ConfigFieldDef:
    return field(key, CONFIG_TYPE_STRING, display_name, *opts)


class SchemaWriter:
    """Writes merged Control config_schema entries into a dict."""

    def __init__(self, into: Dict[str, Any]) -> None:
        self._into = into

    def add(self, key: str, f: ConfigField) -> None:
        m: Dict[str, Any] = {
            "type": f.type,
            "displayName": f.display_name,
            "required": f.required,
        }
        if f.default is not None:
            m["default"] = f.default
        self._into[key] = m


def new_schema_writer(into: Optional[Dict[str, Any]] = None) -> SchemaWriter:
    target = into if into is not None else {}
    return SchemaWriter(target)


def write_schema(sw: Optional[SchemaWriter], prefix: str, defs: List[ConfigFieldDef]) -> None:
    if sw is None:
        return
    for d in defs:
        sw.add(prefix + d.key, d.field)


def config_schema_has_keys(schema: Mapping[str, Any]) -> bool:
    return len(schema) > 0

