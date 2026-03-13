"""Tests for agentruntime-mcp runtime and config."""
import os
import tempfile
from pathlib import Path

import pytest

from agentruntime.mcp.runtime import load_config, make_server


def test_load_config_missing():
    """Missing config returns empty dict."""
    cfg = load_config("nonexistent.yaml")
    assert cfg == {}


def test_load_config_valid():
    """Valid config is loaded."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        f.write(
            b"""
server:
  name: TestServer
  port: 9000
auth:
  mode: token
tracing:
  enabled: false
config:
  key:
    type: string
"""
        )
        path = f.name
    try:
        cfg = load_config(path)
        assert cfg.get("server", {}).get("name") == "TestServer"
        assert cfg.get("server", {}).get("port") == 9000
        assert cfg.get("tracing", {}).get("enabled") is False
    finally:
        os.unlink(path)


def test_make_server():
    """make_server creates FastMCP app."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        f.write(
            b"""
server:
  name: TestMCP
auth:
  mode: none
tracing:
  enabled: false
config: {}
"""
        )
        path = f.name
    try:
        app = make_server(path)
        assert app is not None
        assert app.name == "TestMCP"
    finally:
        os.unlink(path)
