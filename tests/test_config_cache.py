import json
from unittest.mock import patch

import pytest

from agentruntime.mcp.config_cache import (
    config_cache_key,
    fetch_control_config_with_retry,
    rate_limit_wait_seconds,
    reset_config_cache_for_test,
    retry_after_from_control_body,
)
from agentruntime.mcp.errors import ControlError


def test_config_cache_key_stable():
    schema = {"api_key": {"type": "string"}}
    ctx = {"instance_id": "inst-1"}
    assert config_cache_key("tok", schema, ctx) == config_cache_key("tok", schema, ctx)


def test_retry_after_from_control_body():
    body = json.dumps({"error": "rate_limited", "details": {"retry_after": 12}})
    assert retry_after_from_control_body(body) == 12


def test_rate_limit_wait_seconds_uses_retry_after():
    exc = ControlError(429, "{}", retry_after_sec=15)
    assert rate_limit_wait_seconds(exc, 0) == 15.0


def test_fetch_control_config_with_retry_429_then_success():
    calls = {"n": 0}

    def fetch_fn(base, token, schema, ctx, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ControlError(429, '{"error":"rate_limited"}', retry_after_sec=1)
        return {"api_key": "ok"}

    with patch.dict("os.environ", {"MCP_CONFIG_RETRY_BUDGET_SEC": "10"}, clear=False):
        cfg = fetch_control_config_with_retry("", "tok", {}, {}, 5.0, fetch_fn)
    assert cfg["api_key"] == "ok"
    assert calls["n"] == 2


def test_reset_config_cache_for_test():
    reset_config_cache_for_test()
