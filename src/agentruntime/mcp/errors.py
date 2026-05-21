"""Error helpers mirroring agentruntime-mcp-go errors.go."""

from __future__ import annotations

import json
from typing import Any


class ErrAdapterNotFound(LookupError):
    def __init__(self, name: str) -> None:
        super().__init__(f'adapter {name!r} not registered')
        self.name = name


class ControlError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"control server returned {status}: {body}".strip())


def human_message_from_control_api_body(body: str) -> str:
    body = body.strip()
    if not body:
        return ""
    try:
        m = json.loads(body)
        if isinstance(m, dict) and isinstance(m.get("message"), str):
            return m["message"].strip()
    except Exception:
        return ""
    return ""
