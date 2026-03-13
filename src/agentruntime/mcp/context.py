from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, Dict, Iterable, Mapping, Optional


_current_token: ContextVar[Optional[str]] = ContextVar("agentruntime_mcp_auth_token", default=None)
_current_config: ContextVar["ConfigView"] = ContextVar("agentruntime_mcp_resolved_config", default=None)  # type: ignore[assignment]


class ConfigView(dict):
    """Dictionary with attribute access for config values."""

    def __init__(self, data: Optional[Mapping[str, Any]] = None) -> None:
        super().__init__()
        if data:
            for k, v in data.items():
                self[k] = _to_config_value(v)

    def __getattr__(self, item: str) -> Any:
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = _to_config_value(value)

    def copy(self) -> "ConfigView":
        return ConfigView(self)


def _to_config_value(value: Any) -> Any:
    if isinstance(value, ConfigView):
        return value
    if isinstance(value, Mapping):
        return ConfigView(value)
    if isinstance(value, list):
        return [_to_config_value(v) for v in value]
    return value


def set_request_context(token: Optional[str], config: Optional[Mapping[str, Any]]) -> tuple[Token, Token]:
    cfg = ConfigView(config or {})
    t1 = _current_token.set(token)
    t2 = _current_config.set(cfg)
    return t1, t2


def reset_request_context(tokens: Iterable[Token]) -> None:
    t = list(tokens)
    if len(t) >= 1:
        _current_token.reset(t[0])
    if len(t) >= 2:
        _current_config.reset(t[1])


def get_auth_token() -> Optional[str]:
    return _current_token.get()


def get_config() -> ConfigView:
    cfg = _current_config.get()
    if cfg is None:
        return ConfigView({})
    return cfg


def attach_config_to_ctx(ctx: Any, config: Optional[Mapping[str, Any]] = None) -> None:
    if ctx is None:
        return
    cfg = ConfigView(config or get_config())
    try:
        setattr(ctx, "config", cfg)
    except Exception:
        pass
