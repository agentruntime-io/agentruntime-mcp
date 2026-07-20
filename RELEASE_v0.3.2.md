# agentruntime-mcp v0.3.2

## Tool hold (`hold=True`)

- `@tool(name="...", hold=True)` — register in dev; exclude from catalog/publish until cleared (default `hold=False`).
- Registry helpers: `held_tool_names()`, `publishable_entries()`, `registered_tool_names()`.
- `mount_tools` unchanged — all registered tools remain callable in dev (phase 1).

Parity with Go `agentruntime-mcp-go@v0.3.2` and `@agentruntime-labs/agentruntime-mcp@0.3.2`.

See [TOOL_HOLD.md](https://github.com/agentruntime-io/agentruntime/blob/main/connectors/docs/TOOL_HOLD.md) in the monorepo for the full plan.
