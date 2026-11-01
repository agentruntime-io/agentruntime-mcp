# agentruntime-mcp v0.3.5

## Read-only labels on `@tool`

- **`read_only`** on the `@tool` decorator becomes `annotations.readOnlyHint` in `tools/list`. `False` is sent too, so it stays distinct from "not given". Leave it out and control-service infers the label from the tool name and shows it as inferred.
- **`annotations`** on the decorator passes any other MCP tool annotations through.

A changed hint reaches the platform on control's 15-minute schema check, without a manual publish. No breaking changes; connectors pinned to 0.3.3 or 0.3.4 keep working.
