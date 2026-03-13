from __future__ import annotations

import json
import os
from typing import Any, Dict

TEMPLATE_HEADER = """from fastmcp import FastMCP
from pydantic import BaseModel, Field
import httpx

app = FastMCP(name="OpenAPI_MCP")

def _client():
    return httpx.Client(timeout=10)
"""


def generate(openapi_file: str, output_py: str) -> None:
    with open(openapi_file, "r", encoding="utf-8") as f:
        spec: Dict[str, Any] = json.load(f)

    code = [TEMPLATE_HEADER]
    base_url = spec.get("servers", [{}])[0].get("url", "")

    paths = spec.get("paths", {})
    for path, methods in paths.items():
        for method, op in methods.items():
            if method.lower() not in {"get", "post"}:
                continue
            op_id = op.get("operationId") or (method + "_" + path.strip("/").replace("/", "_").replace("-", "_") or "root")
            fn_name = f"tool_{op_id}"
            url_expr = base_url.rstrip("/") + path
            code.append(f"\n@app.tool(name=\"{op_id}\")\ndef {fn_name}(**kwargs):\n    \"\"\"Generated from OpenAPI {method.upper()} {path}\n    kwargs are sent as JSON for POST or as params for GET\n    \"\"\"\n    with _client() as c:\n        if '{method.lower()}' == 'get':\n            r = c.get(\"{url_expr}\", params=kwargs)\n        else:\n            r = c.post(\"{url_expr}\", json=kwargs)\n        r.raise_for_status()\n        return {{'structuredContent': r.json()}}\n")

    os.makedirs(os.path.dirname(output_py), exist_ok=True)
    with open(output_py, "w", encoding="utf-8") as f:
        f.write("\n".join(code))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("-i", "--input", required=True, help="openapi.json path")
    p.add_argument("-o", "--output", default="generated/openapi_tools.py")
    args = p.parse_args()
    generate(args.input, args.output)


