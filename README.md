# AgentRuntime MCP SDK (Python)

Opinionated SDK for MCP connectors using **FastMCP** with the same **Control** integration as [`agentruntime-mcp-go`](https://github.com/agentruntime-io/agentruntime-mcp-go): optional `POST /mcp/config`, env merge, and request metadata (run token, instance id).

There is **no mandatory legacy standalone token/HMAC middleware chain** in front of every request. Probe-style auth is the **Bearer run token** (or `X-MCP-Token`) and headers AgentRuntime sends; optional `auth.mode` in `config.yaml` is reserved for future templates and does not switch Control gating off.

## Install

```bash
pip install agentruntime-mcp
```

## Runtimes

| Entry | When to use | HTTP |
|--------|-------------|------|
| **`run(config_path)`** | Decorator-only `tool()` modules; tools registered from `config.yaml` / `build_schemas` | `/mcp` |
| **`run_with_registry(config_path, *names)`** | Plugins registered with **`register_adapter`**; one process, one MCP server | `/mcp` |
| **`run_with_router(config_path)`** | Same registry, **monolith routing** (Go **`RunWithRouter`** / TS **`runWithRouter`** parity) | `/{adapter}/mcp` plus optional **webhook** routes on the **same** ASGI app |

Use **`register_adapter`** for anything that should share a process with other adapters. Keep plain **`run()`** for single-connector demos that only use decorators and YAML tools.

**Webhooks:** Implement **`register_webhook(self, mux: ServeMux)`** on the adapter. Paths are registered on the **root** Starlette app **before** adapter mounts (same dispatch order as Go/TS). Operators expose vendor callbacks as `https://<host>:<port><path>` (same host/port as MCP).

## Minimal example

```python
from pydantic import BaseModel, Field
from agentruntime.mcp.decorators import tool
from agentruntime.mcp.runtime import run
from fastmcp import Context

class In(BaseModel):
    a: float = Field(...)
    b: float = Field(...)

class Out(BaseModel):
    result: float
    expression: str

@tool(name="add", input_model=In, output_model=Out)
def add(a: float, b: float, ctx: Context) -> Out:
    region = ctx.config.region  # resolved config when schema + Control are used
    return Out(result=a + b, expression=f"{a} + {b}")

if __name__ == "__main__":
    run("config.yaml")
```

## Config (`config.yaml`)

- **`server`:** `name`, `host`, `port`, `stateless_http`
- **`tracing`:** enable OpenTelemetry when dependencies are present
- **`config`:** declarative schema for Control / `GET /mcp/config/schema`

Env overrides: **`HOST`**, **`PORT`** (see [`docs/mcp/mcp_env.md`](../../docs/mcp/mcp_env.md)).

Example:

```yaml
server:
  name: "MyConnector"
  host: "127.0.0.1"
  port: 8012
  stateless_http: true

tracing:
  enabled: false

config:
  apiKey:
    type: string
    displayName: API Key
    required: true
```

## Control config resolution

When the adapter registers at least one config key:

- Set **`MCP_CONTROL_SERVER_URL`** to your control-service base URL.
- The SDK may call **`POST /mcp/config`** with the run token from the request and your schema.
- Set **`MCP_CONFIG_FETCH_REQUIRED=false`** for local work without Control (when you still declare schema keys).

See [`docs/mcp/mcp_env.md`](../../docs/mcp/mcp_env.md) for the full variable list.

## Proxy (library)

```python
from agentruntime.mcp.proxy import run_proxy
run_proxy(
    target_url="http://127.0.0.1:8000/mcp",
    overlay_file="tools.yaml",
    host="127.0.0.1",
    port=8010,
)
```

## Tool organization (`toolorg`)

Large connectors can build publish metadata for Control catalog grouping. Parity with Go `toolorg` — see [MCP_SDK_PARITY.md](../../docs/mcp/MCP_SDK_PARITY.md).

```python
from agentruntime.mcp.toolorg import publisher_metadata, Metadata

meta = publisher_metadata("clickup_get_task", Metadata())
# → display_name, suggested_group, suggested_tags for mcp_tools.metadata
```

Per-request caller bearer (for downstream HTTP): `request_bearer_from_context()`.

## TypeScript sibling SDK

For Node deployments, use the monorepo package [`packages/agentruntime-mcp-ts`](../agentruntime-mcp-ts/README.md) (`@agentruntime-labs/agentruntime-mcp`): official **`@modelcontextprotocol/server`**, Zod 4, **`runWithRouter`**.

## Examples in this repo

- [`connectors/py-connectors/resend-connector`](../../connectors/py-connectors/resend-connector/) — Python Resend connector (illustrative layout)

## Releasing

See [`../RELEASE.md`](../RELEASE.md) (Python section): lightweight Git tags (`v0.1.0`, `v0.1.1`), bump `version` in `pyproject.toml`, do not commit `__pycache__` / `*.egg-info/`.
