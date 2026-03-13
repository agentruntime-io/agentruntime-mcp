from __future__ import annotations

from typing import Callable, Optional, Type, Any, Dict, List, Tuple
import inspect
from functools import wraps
from pydantic import BaseModel
from fastmcp import FastMCP
from .context import attach_config_to_ctx, get_config


class ToolRegistry:
    def __init__(self) -> None:
        self.entries: List[Dict[str, Any]] = []

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        input_model: Optional[Type[BaseModel]],
        output_model: Optional[Type[BaseModel]],
        description: Optional[str],
    ) -> None:
        self.entries.append(
            {
                "name": name,
                "func": func,
                "in_model": input_model,
                "out_model": output_model,
                "desc": (description or "").strip() or None,
            }
        )


registry = ToolRegistry()


def tool(
    name: str,
    input_model: Optional[Type[BaseModel]] = None,
    output_model: Optional[Type[BaseModel]] = None,
    description: Optional[str] = None,
):
    def deco(func: Callable[..., Any]) -> Callable[..., Any]:
        registry.register(name, func, input_model, output_model, description or getattr(func, "__doc__", None))
        return func

    return deco


def mount_tools(
    mcp: FastMCP,
    schema_builder: Callable[[Optional[type], Optional[type]], Tuple[Dict[str, Any], Dict[str, Any]]],
) -> List[Tuple[Dict[str, Any], Callable[..., Any]]]:
    """Expose tools from the registry on the given FastMCP app and add tools/list."""
    exposed: List[Tuple[Dict[str, Any], Callable[..., Any]]] = []
    for e in registry.entries:
        raw_fn = e["func"]
        s_in, s_out = schema_builder(e.get("in_model"), e.get("out_model"))
        tool_kwargs: Dict[str, Any] = {"name": e["name"]}
        if e.get("out_model") and s_out:
            s_out_copy = dict(s_out)
            if "type" not in s_out_copy:
                s_out_copy["type"] = "object"
            tool_kwargs["output_schema"] = s_out_copy
        if inspect.iscoroutinefunction(raw_fn):
            @wraps(raw_fn)
            async def wrapped_async(*args, __fn=raw_fn, **kwargs):
                cfg = get_config()
                for a in args:
                    attach_config_to_ctx(a, cfg)
                for v in kwargs.values():
                    attach_config_to_ctx(v, cfg)
                return await __fn(*args, **kwargs)

            exposed_fn = mcp.tool(**tool_kwargs)(wrapped_async)  # type: ignore[arg-type]
        else:
            @wraps(raw_fn)
            def wrapped_sync(*args, __fn=raw_fn, **kwargs):
                cfg = get_config()
                for a in args:
                    attach_config_to_ctx(a, cfg)
                for v in kwargs.values():
                    attach_config_to_ctx(v, cfg)
                return __fn(*args, **kwargs)

            exposed_fn = mcp.tool(**tool_kwargs)(wrapped_sync)  # type: ignore[arg-type]
        exposed.append((e, exposed_fn))

    @mcp.tool(name="list_tools")
    def list_tools() -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        for e, _ in exposed:
            s_in, s_out = schema_builder(e.get("in_model"), e.get("out_model"))
            items.append(
                {
                    "name": e["name"],
                    "description": e.get("desc"),
                    "inputSchema": s_in,
                    "outputSchema": s_out,
                }
            )
        return {"tools": items}

    return exposed


