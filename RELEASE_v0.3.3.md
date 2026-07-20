# agentruntime-mcp v0.3.3

## Tool schema: explicit defaults

- **`emit_json_shape`** — emits JSON Schema `default` when a Pydantic field has an explicit `Field(default=…)` (does not emit `None` for optional fields).
- **`Enum` / `Literal`** — unchanged; already emitted as schema `enum`.

Parity with `agentruntime-mcp-go@v0.3.3` and `@agentruntime-labs/agentruntime-mcp@0.3.3`.
