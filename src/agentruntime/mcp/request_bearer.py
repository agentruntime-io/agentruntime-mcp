"""Per-request bearer token context (parity with agentruntime-mcp-go request_bearer)."""

from __future__ import annotations

from .context import get_auth_token

__all__ = ["request_bearer_from_context"]


def request_bearer_from_context() -> str | None:
    """Return the incoming MCP caller bearer token for the active request, if set."""
    return get_auth_token()
