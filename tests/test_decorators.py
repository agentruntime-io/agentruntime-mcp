from agentruntime.mcp.decorators import (
    registry,
    tool,
    registered_tool_names,
    held_tool_names,
    publishable_entries,
)


def setup_module() -> None:
    registry.entries.clear()


def test_tool_hold_registry() -> None:
    setup_module()

    @tool(name="pub_tool")
    def pub_tool() -> None:
        """publishable"""

    @tool(name="held_tool", hold=True)
    def held_tool() -> None:
        """held"""

    assert registered_tool_names() == ["pub_tool", "held_tool"]
    assert held_tool_names() == ["held_tool"]
    assert [e["name"] for e in publishable_entries()] == ["pub_tool"]
