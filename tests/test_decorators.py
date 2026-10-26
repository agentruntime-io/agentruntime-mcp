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


def test_tool_annotations_registry() -> None:
    setup_module()

    @tool(name="acme_list_items", read_only=True)
    def list_items() -> None:
        """read"""

    @tool(name="acme_get_updates", read_only=False)
    def get_updates() -> None:
        """acknowledges what it reads"""

    @tool(name="acme_send", annotations={"destructiveHint": False, "title": "Send"})
    def send() -> None:
        """adds"""

    @tool(name="acme_list_users")
    def list_users() -> None:
        """no hint: the platform infers it"""

    by_name = {e["name"]: e["annotations"] for e in registry.entries}
    assert by_name["acme_list_items"] == {"readOnlyHint": True}
    # Explicit False is kept (not dropped as "not given").
    assert by_name["acme_get_updates"] == {"readOnlyHint": False}
    assert by_name["acme_send"] == {"destructiveHint": False, "title": "Send"}
    assert by_name["acme_list_users"] is None


def test_tool_annotations_reach_tools_list() -> None:
    import asyncio

    from fastmcp import Client, FastMCP

    from agentruntime.mcp.decorators import mount_tools

    setup_module()

    @tool(name="acme_list_items", read_only=True)
    def list_items() -> str:
        """read"""
        return "ok"

    @tool(name="acme_get_updates", read_only=False)
    def get_updates() -> str:
        """acknowledges what it reads"""
        return "ok"

    @tool(name="acme_list_users")
    def list_users() -> str:
        """no hint"""
        return "ok"

    app = FastMCP("test")
    mount_tools(app, lambda i, o: ({}, {}))

    async def listed() -> dict:
        async with Client(app) as client:
            tools = await client.list_tools()
        return {t.name: t.model_dump(by_alias=True, exclude_none=True).get("annotations") for t in tools}

    got = asyncio.run(listed())
    assert got["acme_list_items"]["readOnlyHint"] is True
    assert got["acme_get_updates"]["readOnlyHint"] is False
    assert not (got["acme_list_users"] or {}).get("readOnlyHint")
    assert "readOnlyHint" not in (got["acme_list_users"] or {})
