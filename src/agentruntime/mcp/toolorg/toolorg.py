"""Publish-time tool organization — mirror agentruntime-mcp-go/toolorg."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

_DEFAULT_GROUP_LABELS: dict[str, str] = {
    "hierarchy": "Hierarchy",
    "tasks": "Tasks",
    "search_members": "Search & members",
    "comments": "Comments",
    "time": "Time tracking",
    "docs": "Docs",
    "chat": "Chat",
    "uncategorized": "Other",
}


@dataclass
class Metadata:
    display_name: str = ""
    suggested_group: str = ""
    suggested_tags: list[str] = field(default_factory=list)
    suggested_rank_key: str = ""


@dataclass
class EffectiveOrganization:
    group_id: str = ""
    group_label: str = ""
    rank_key: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class ToolGroup:
    id: str = ""
    label: str = ""
    rank_key: str = ""
    source: str = ""


def _normalize_tags(tags: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        t = str(t).strip().lower()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    out.sort()
    return out


def _infer_group_id(body: str) -> str:
    if "chat" in body:
        return "chat"
    if "doc" in body:
        return "docs"
    if "comment" in body:
        return "comments"
    if "time" in body:
        return "time"
    if body == "search" or "member" in body or "assignee" in body or "filtered_team" in body:
        return "search_members"
    if (
        "workspace" in body
        or "space" in body
        or "folder" in body
        or "hierarchy" in body
        or body == "get_list"
        or body.startswith("get_lists")
        or body.startswith("create_list")
        or body.startswith("update_list")
        or body.startswith("create_folder")
        or body.startswith("update_folder")
    ):
        return "hierarchy"
    return "tasks"


def _is_read_only_verb(body: str) -> bool:
    for prefix in ("get_", "list_", "find_", "resolve_", "search"):
        if body.startswith(prefix) or body == prefix.rstrip("_"):
            return True
    return False


def _infer_tags(body: str, group_id: str) -> list[str]:
    tags = [group_id]
    tags.append("read_only" if _is_read_only_verb(body) else "mutating")
    tags.append("v3" if ("chat" in body or "doc" in body) else "v2")
    return _normalize_tags(tags)


def suggest_from_wire_name(tool_name: str) -> tuple[str, list[str]]:
    name = tool_name.strip().lower()
    parts = name.split("_")
    if len(parts) < 2:
        return "uncategorized", ["mutating"]
    body = "_".join(parts[1:])
    group_id = _infer_group_id(body)
    return group_id, _infer_tags(body, group_id)


def format_display_name(tool_name: str) -> str:
    parts = tool_name.strip().split("_")
    if len(parts) <= 1:
        return tool_name
    body = " ".join(parts[1:])
    if not body:
        return tool_name
    return body[0].upper() + body[1:]


def publisher_metadata(tool_name: str, overrides: Optional[Metadata] = None) -> dict[str, Any]:
    ov = overrides or Metadata()
    out: dict[str, Any] = {}
    display = ov.display_name.strip()
    if not display:
        display = format_display_name(tool_name)
    if display:
        out["display_name"] = display
    group = ov.suggested_group.strip().lower()
    if not group:
        group, _ = suggest_from_wire_name(tool_name)
    if group:
        out["suggested_group"] = group
    tags = list(ov.suggested_tags)
    if not tags:
        _, tags = suggest_from_wire_name(tool_name)
    if tags:
        out["suggested_tags"] = tags
    rk = ov.suggested_rank_key.strip()
    if rk:
        out["suggested_rank_key"] = rk
    return out


def default_publisher_metadata(tool_name: str) -> dict[str, Any]:
    return publisher_metadata(tool_name, Metadata())


def group_label(group_id: str) -> str:
    gid = group_id.strip().lower()
    if gid in _DEFAULT_GROUP_LABELS:
        return _DEFAULT_GROUP_LABELS[gid]
    parts = gid.split("_")
    titled = []
    for p in parts:
        if not p:
            continue
        titled.append(p[0].upper() + p[1:])
    return " ".join(titled)


def _normalize_group_id(group_id: str) -> str:
    return group_id.strip().lower().replace(" ", "_")


def parse_metadata(raw: bytes | str) -> Metadata:
    if not raw:
        return Metadata()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace")
    else:
        text = raw
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return Metadata()
    if not isinstance(parsed, dict):
        return Metadata()
    tags_raw = parsed.get("suggested_tags") or []
    tags: list[str] = []
    if isinstance(tags_raw, list):
        tags = [str(t) for t in tags_raw]
    return Metadata(
        display_name=str(parsed.get("display_name") or ""),
        suggested_group=_normalize_group_id(str(parsed.get("suggested_group") or "")),
        suggested_tags=_normalize_tags(tags),
        suggested_rank_key=str(parsed.get("suggested_rank_key") or ""),
    )


def metadata_is_empty(meta: Mapping[str, Any]) -> bool:
    if not meta:
        return True
    for k, v in meta.items():
        if v is None:
            continue
        if k == "suggested_tags":
            if isinstance(v, list) and len(v) > 0:
                return False
            continue
        if isinstance(v, str) and v.strip():
            return False
    return True


def merge_effective(
    published: Metadata,
    overlay_group_id: Optional[str] = None,
    overlay_rank_key: Optional[str] = None,
) -> EffectiveOrganization:
    group_id = published.suggested_group.strip()
    tags = list(published.suggested_tags)
    if overlay_group_id is not None:
        g = _normalize_group_id(overlay_group_id)
        if g:
            group_id = g
    rank_key = published.suggested_rank_key.strip()
    if overlay_rank_key is not None:
        rk = overlay_rank_key.strip()
        if rk:
            rank_key = rk
    return EffectiveOrganization(
        group_id=group_id,
        group_label=group_label(group_id),
        rank_key=rank_key,
        tags=tags,
    )
