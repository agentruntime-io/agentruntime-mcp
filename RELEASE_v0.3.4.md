# agentruntime-mcp v0.3.4

## Control config cache and 429 retry

Parity with `agentruntime-mcp-go@v0.3.8` control-config path (Python connectors do not ship OAuth middleware in this release).

### New module: `config_cache`

- **`fetch_control_config_cached`** — in-process TTL cache (30–120s, `MCP_CONFIG_CACHE_TTL_SEC`) with singleflight deduplication per token/instance/schema key.
- **`fetch_control_config_with_retry`** — retries Control `POST /mcp/config` on HTTP 429 within `MCP_CONFIG_RETRY_BUDGET_SEC` (default 30s).
- **`retry_after_from_control_body`** — parses `retry_after` from Control JSON body (`details.retry_after`).

### Updated APIs

- **`ControlError`** — new `retry_after_sec` field; populated from `Retry-After` header or response body.
- **`ControlConfigMiddleware`** — uses cached fetch path instead of direct HTTP on every request.
- **`fetch_control_payload`** — surfaces `retry_after_sec` on 429 responses.

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_CONFIG_CACHE_TTL_SEC` | `60` | Cache TTL (clamped 30–120) |
| `MCP_CONFIG_RETRY_BUDGET_SEC` | `30` | Max wall time for 429 retries |

## Upgrade

```bash
pip install -U agentruntime-mcp==0.3.4
```
