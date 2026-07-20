from enum import Enum

from pydantic import BaseModel, Field

from agentruntime.mcp.schemas import emit_json_shape


class Mode(str, Enum):
    fast = "fast"
    accurate = "accurate"


class SampleInput(BaseModel):
    limit: int = Field(default=30, ge=1, le=100)
    mode: Mode
    note: str | None = None


def test_emit_json_shape_explicit_default() -> None:
    shape = emit_json_shape(SampleInput)
    props = shape["properties"]
    assert props["limit"]["default"] == 30
    assert props["mode"]["enum"] == ["fast", "accurate"]
    assert "default" not in props["note"]


def test_emit_json_shape_required_field_has_no_default() -> None:
    class RequiredOnly(BaseModel):
        task_id: str

    shape = emit_json_shape(RequiredOnly)
    assert "default" not in shape["properties"]["task_id"]
