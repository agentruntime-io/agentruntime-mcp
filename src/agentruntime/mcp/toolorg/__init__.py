"""Tool organization helpers for MCP publish metadata (parity with agentruntime-mcp-go/toolorg)."""

from .toolorg import (
    Metadata,
    EffectiveOrganization,
    ToolGroup,
    suggest_from_wire_name,
    format_display_name,
    publisher_metadata,
    default_publisher_metadata,
    group_label,
    parse_metadata,
    metadata_is_empty,
    merge_effective,
)

__all__ = [
    "Metadata",
    "EffectiveOrganization",
    "ToolGroup",
    "suggest_from_wire_name",
    "format_display_name",
    "publisher_metadata",
    "default_publisher_metadata",
    "group_label",
    "parse_metadata",
    "metadata_is_empty",
    "merge_effective",
]
