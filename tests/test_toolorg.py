"""Tests for toolorg parity with agentruntime-mcp-go/toolorg."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentruntime.mcp.toolorg import (
    Metadata,
    default_publisher_metadata,
    merge_effective,
    suggest_from_wire_name,
)


def _load_cases() -> list[dict]:
    path = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "agentruntime"
        / "mcp"
        / "toolorg"
        / "fixtures"
        / "suggest_cases.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["tool_name"])
def test_suggest_from_wire_name_fixtures(case: dict) -> None:
    group, tags = suggest_from_wire_name(case["tool_name"])
    assert group == case["group"]
    assert tags == case["tags"]


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["tool_name"])
def test_default_publisher_metadata_fixtures(case: dict) -> None:
    meta = default_publisher_metadata(case["tool_name"])
    assert meta["suggested_group"] == case["group"]


def test_merge_effective_explicit_only() -> None:
    eff = merge_effective(Metadata(), overlay_group_id="docs", overlay_rank_key="n")
    assert eff.group_id == "docs"
    assert eff.rank_key == "n"

    eff = merge_effective(Metadata(suggested_group="tasks"))
    assert eff.group_id == "tasks"

    eff = merge_effective(Metadata())
    assert eff.group_id == ""
    assert eff.tags == []
