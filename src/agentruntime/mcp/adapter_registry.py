"""Adapter registry mirroring agentruntime-mcp-go adapter.go."""

from __future__ import annotations

from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Protocol,
    Tuple,
    runtime_checkable,
)

from .errors import ErrAdapterNotFound

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from .config_schema import SchemaWriter


@runtime_checkable
class Adapter(Protocol):
    def register(self, mcp: "FastMCP", schema: "SchemaWriter") -> None: ...


@runtime_checkable
class WebhookAdapter(Protocol):
    def register_webhook(self, mux: "ServeMux") -> None: ...


@dataclass(frozen=True)
class AdapterConstructorInput:
    """Reserved for future use (parity with Go AdapterConstructorInput)."""


AdapterConstructor = Callable[[AdapterConstructorInput], Adapter]


class ServeMux:
    """HTTP route table (exact path → handler). Order preserved (first match wins when iterating).

    Handlers should be Starlette-style ``async def(request: Request) -> Response``.
    """

    def __init__(self) -> None:
        self._routes: List[Tuple[str, Any]] = []

    def handle(self, path: str, handler: Any) -> None:
        self._routes.append((normalize_path(path), handler))

    def __iter__(self) -> Iterable[Tuple[str, Any]]:
        return iter(self._routes)


def normalize_path(path: str) -> str:
    if not path or path == "/":
        return "/"
    return path[:-1] if path.endswith("/") else path


_registry: Dict[str, AdapterConstructor] = {}


def register_adapter(name: str, ctor: AdapterConstructor) -> None:
    _registry[name] = ctor


def list_adapter_names() -> List[str]:
    return sorted(_registry.keys())


def instantiate_adapters(names: List[str]) -> List[Adapter]:
    inp = AdapterConstructorInput()
    if not names:
        return [ctor(inp) for ctor in _registry.values()]
    out: List[Adapter] = []
    for n in names:
        ctor = _registry.get(n)
        if ctor is None:
            raise ErrAdapterNotFound(n)
        out.append(ctor(inp))
    return out
