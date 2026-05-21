from __future__ import annotations

import pytest

from agentruntime.mcp.adapter_registry import ServeMux, normalize_path
from agentruntime.mcp.errors import ErrAdapterNotFound
from agentruntime.mcp.runtime import run_with_router


def test_normalize_path() -> None:
    assert normalize_path("/a/") == "/a"
    assert normalize_path("/") == "/"


def test_serve_mux_iteration_order() -> None:
    m = ServeMux()
    m.handle("/first", lambda _r: None)
    m.handle("/second", lambda _r: None)
    assert [p for p, _ in m] == ["/first", "/second"]


def test_run_with_router_requires_registered_adapters() -> None:
    import agentruntime.mcp.adapter_registry as reg

    saved = dict(reg._registry)
    reg._registry.clear()
    try:
        with pytest.raises(ErrAdapterNotFound):
            run_with_router("___mcp_test_missing_config___.yaml")
    finally:
        reg._registry.clear()
        reg._registry.update(saved)
