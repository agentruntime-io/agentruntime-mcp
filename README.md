# AgentRuntime MCP SDK (Python)

Opinionated SDK for building MCP agents with FastMCP.

## Install
```bash
pip install agentruntime-mcp
```

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
    # Resolved config from control server is exposed here.
    region = ctx.config.region  # or ctx.config["region"]
    return Out(result=a+b, expression=f"{a} + {b}")

if __name__ == "__main__":
    run("config.yaml")
```

## Config
- `config.yaml` controls server host/port, auth mode, and tracing.  
- Env overrides: `HOST`, `PORT`, `MCP_AUTH_MODE`.

Example `config.yaml`:
```yaml
server:
  name: "MCPAuthDemo"
  host: "127.0.0.1"
  port: 8012
  stateless_http: true

auth:
  mode: token   # token|hmac|none

tracing:
  enabled: false

config:
  accessKeyId:
    type: string
    displayName: Access Key ID
    required: true
  secretAccessKey:
    type: string
    displayName: Secret Access Key
    required: true
  bucket:
    type: string
    displayName: Bucket
    required: true
  endpoint:
    type: string
    displayName: Endpoint
    required: false
  region:
    type: option
    displayName: Region
    required: true
    options:
      - label: Default
        value: us-east-1
      - label: US East (Ohio) [us-east-2]
        value: us-east-2
```

Auth modes
- `none`: no auth
- `token`: `Authorization: Bearer <token>` or `X-MCP-Token`; dev fallback `?auth_token=` if `ALLOW_QUERY_TOKEN=true`
- `hmac`: headers `X-MCP-KeyId`, `X-MCP-Timestamp` (unix seconds), `X-MCP-Signature` (hex(HMAC-SHA256(secret, `${ts}\n${method}\n${path}`)))

## Control config resolution

The SDK can resolve populated config values from a control server and expose
them on request context as `ctx.config`.

- Set `MCP_CONTROL_SERVER_URL` (e.g. `http://control-svc:8080`)
- SDK sends `POST /mcp/config` with your `config.yaml` `config:` schema
- SDK forwards auth token from middleware (`Authorization` / `X-MCP-Token`)
- SDK also forwards best-effort `runtime_context` for control-side policy/resolution
  (tool name plus optional request metadata from headers/query such as
  `server_id`, `run_id`, `workflow_id`, `call_id`, `trigger_type`, `trigger_id`,
  `instance_id`, `connection_ids`, `tenant_id_hint`, `project_id_hint`)
- Returned populated config is exposed as:
  - `ctx.config.name`
  - `ctx.config["name"]`

Environment flags:
- `MCP_CONTROL_SERVER_URL`: control server base URL
- `MCP_CONTROL_TIMEOUT_SEC`: request timeout (default `5`)
- `MCP_CONFIG_FETCH_REQUIRED`: fail request if resolution fails (default `true`)

Schema endpoint:
- `GET /mcp/config/schema` returns the raw `config:` schema from `config.yaml`.

## Proxy (library)
```python
from agentruntime.mcp.proxy import run_proxy
run_proxy(target_url="http://127.0.0.1:8000/mcp", overlay_file="tools.yaml", host="127.0.0.1", port=8010)
```

## Templates

Example MCP server using this SDK:

- [connectors/py-connectors/resend-connector](../../connectors/py-connectors/resend-connector/) – Resend (send_email, list_audiences)
