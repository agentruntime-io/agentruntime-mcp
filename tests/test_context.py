"""Tests for agentruntime-mcp context."""
from agentruntime.mcp.context import ConfigView, get_config, set_request_context, reset_request_context


def test_config_view():
    """ConfigView allows attribute and dict access."""
    cv = ConfigView({"region": "us-east-1", "nested": {"key": "val"}})
    assert cv["region"] == "us-east-1"
    assert cv.region == "us-east-1"
    assert cv.nested["key"] == "val"
    assert cv.nested.key == "val"


def test_set_get_request_context():
    """Request context can be set and retrieved."""
    tokens = set_request_context("token123", {"api_key": "secret"})
    try:
        cfg = get_config()
        assert cfg["api_key"] == "secret"
        assert cfg.api_key == "secret"
    finally:
        reset_request_context(tokens)
