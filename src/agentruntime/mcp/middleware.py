from __future__ import annotations

import contextvars
import logging
import os
import traceback
import asyncio
import json
import uuid
from typing import Any, Dict, Optional
import time
import hmac
import hashlib
from urllib import error as urlerror
from urllib import request as urlrequest

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.dependencies import get_http_request
from starlette.responses import JSONResponse
from .context import attach_config_to_ctx, reset_request_context, set_request_context

# Context var for HTTP request when processing initialize in stateless mode.
# Patched MiddlewareServerSession sets this from responder.message_metadata.request_context
# before middleware runs, so AuthToken and ControlConfig can read the token.
_http_request_ctx: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "agentruntime_http_request", default=None
)


def _patch_middleware_session_for_stateless_request_context() -> None:
    """Patch MiddlewareServerSession to set HTTP request in context var before middleware runs.

    In stateless HTTP mode, each request runs in a new async task. The session processes
    the request in that task, but the HTTP request (and Authorization header) lives in
    the transport layer. FastMCP's middleware runs before request_ctx is set, so our
    AuthToken and ControlConfig middleware cannot read the token.

    The RequestResponder has message_metadata.request_context (the Starlette Request).
    We patch _received_request to set it in _http_request_ctx before calling
    _apply_middleware, so our middleware can extract the Bearer token.
    """
    try:
        from fastmcp.server.low_level import MiddlewareServerSession

        _original_received_request = MiddlewareServerSession._received_request

        async def _patched_received_request(self: Any, responder: Any) -> Any:
            http_req = None
            if responder is not None and hasattr(responder, "message_metadata"):
                meta = responder.message_metadata
                if meta is not None:
                    # ServerMessageMetadata has request_context; accept any object with it
                    http_req = getattr(meta, "request_context", None)


            token = None
            if http_req is not None:
                try:
                    token = _http_request_ctx.set(http_req)
                except Exception:
                    pass

            try:
                return await _original_received_request(self, responder)
            finally:
                if token is not None:
                    try:
                        _http_request_ctx.reset(token)
                    except Exception:
                        pass

        MiddlewareServerSession._received_request = _patched_received_request
    except Exception as e:
        logging.getLogger(__name__).warning(
            "Could not patch MiddlewareServerSession for stateless request context: %s", e
        )

# Enable MCP SDK debug logging when MCP_DEBUG_INITIALIZE=1 (captures Pydantic validation errors)
if os.getenv("MCP_DEBUG_INITIALIZE", "").strip() in ("1", "true", "yes"):
    logging.getLogger("mcp").setLevel(logging.DEBUG)
    logging.getLogger("mcp.shared.session").setLevel(logging.DEBUG)


# ---- OpenTelemetry (OTLP over HTTP to local collector/jaeger) ----
# Skip setup if: config.yaml has tracing.enabled=false, or OTEL_SDK_DISABLED=true
def _should_enable_otel() -> bool:
    if os.getenv("OTEL_SDK_DISABLED", "").lower() in ("true", "1", "yes"):
        return False
    config_path = os.getenv("MCP_CONFIG_PATH") or "config.yaml"
    if not os.path.isabs(config_path):
        config_path = os.path.join(os.getcwd(), config_path)
    if os.path.exists(config_path):
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            if not cfg.get("tracing", {}).get("enabled", True):
                return False
        except Exception:
            pass
    return True


trace: Any = None
TraceContextTextMapPropagator: Any = None
tracer = None
if _should_enable_otel():
    try:
        from opentelemetry import trace  # type: ignore
        from opentelemetry.trace.propagation.tracecontext import (  # type: ignore
            TraceContextTextMapPropagator,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore
        from opentelemetry.sdk.resources import Resource  # type: ignore
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore

        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
        resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "fastmcp-enhanced")})
        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces"))
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        tracer = trace.get_tracer(os.getenv("OTEL_SERVICE_NAME", "fastmcp-enhanced"))

        print("OpenTelemetry setup complete")
    except Exception:
        print("Error setting up OpenTelemetry:")
        print(traceback.format_exc())
        tracer = None


class InitParamsCompatMiddleware(Middleware):
    """Normalizes initialize params for Go MCP client compatibility.
    Ensures capabilities is never null (Python MCP SDK expects an object).
    """

    async def on_request(self, context: MiddlewareContext, call_next):
        req = _request_from_context(context)
        if req is None:
            return await call_next(context)

        try:
            body = await req.body()
            if not body:
                return await call_next(context)
            data = json.loads(body)
            method = data.get("method") if isinstance(data, dict) else None
            if method != "initialize":
                return await call_next(context)

            params = data.get("params")
            if not isinstance(params, dict):
                params = {}
                data["params"] = params

            modified = False
            if params.get("capabilities") is None:
                params["capabilities"] = {}
                modified = True
            ci = params.get("clientInfo")
            if not isinstance(ci, dict):
                params["clientInfo"] = {"name": "agentruntime", "version": "1.0.0"}
                modified = True
            else:
                if not ci.get("name"):
                    params["clientInfo"]["name"] = "agentruntime"
                    modified = True
                if not ci.get("version"):
                    params["clientInfo"]["version"] = "1.0.0"
                    modified = True

            if modified:
                new_body = json.dumps(data, separators=(",", ":")).encode("utf-8")
                object.__setattr__(req, "_body", new_body)

        except Exception as e:
            logging.debug("[InitParamsCompat] could not normalize: %s", e)

        return await call_next(context)


class DebugInitMiddleware(Middleware):
    """Logs incoming initialize request params when MCP_DEBUG_INITIALIZE=1."""

    async def on_request(self, context: MiddlewareContext, call_next):
        if os.getenv("MCP_DEBUG_INITIALIZE", "").strip() not in ("1", "true", "yes"):
            return await call_next(context)

        req = _request_from_context(context)
        if req is None:
            return await call_next(context)

        try:
            body = await req.body()
            if not body:
                return await call_next(context)
            data = json.loads(body)
            method = data.get("method") if isinstance(data, dict) else None
            if method == "initialize":
                params = data.get("params", {})
                logging.warning(
                    "[MCP_DEBUG_INITIALIZE] incoming initialize params: %s",
                    json.dumps(params, indent=2, default=str),
                )
        except Exception as e:
            logging.debug("[MCP_DEBUG_INITIALIZE] could not log body: %s", e)

        return await call_next(context)


class CustomHeaderMiddleware(Middleware):
    async def on_request(self, context: MiddlewareContext, call_next):
        method = getattr(context, "method", "UNKNOWN")
        tool_name = getattr(getattr(context, "message", None), "name", None)

        # If OpenTelemetry isn't available, skip tracing entirely
        if tracer is None or "trace" not in globals() or trace is None or "TraceContextTextMapPropagator" not in globals() or TraceContextTextMapPropagator is None:  # type: ignore[name-defined]
            return await call_next(context)

        def _extract_parent_ctx(req) -> Any:
            propagator = TraceContextTextMapPropagator()

            # Try headers first
            try:
                hdr_ctx = propagator.extract(req.headers)
                hdr_span = trace.get_current_span(hdr_ctx).get_span_context()
                if hdr_span and getattr(hdr_span, "is_valid", False):
                    return hdr_ctx
            except Exception:
                pass

            # Fallback to query parameters (?traceparent=&tracestate=)
            try:
                qp = getattr(req, "query_params", None)
                if qp:
                    carrier: Dict[str, str] = {}
                    tp = qp.get("traceparent")
                    ts = qp.get("tracestate")
                    if tp:
                        carrier["traceparent"] = tp
                    if ts:
                        carrier["tracestate"] = ts
                    if carrier:
                        q_ctx = propagator.extract(carrier)
                        q_span = trace.get_current_span(q_ctx).get_span_context()
                        if q_span and getattr(q_span, "is_valid", False):
                            return q_ctx
            except Exception:
                pass

            return None

        parent_ctx: Any = None
        try:
            fast_ctx = getattr(context, "fastmcp_context", None)
            if fast_ctx is not None and getattr(fast_ctx, "request_context", None) is not None:
                req = getattr(fast_ctx.request_context, "request", None)
                if req is not None:
                    parent_ctx = _extract_parent_ctx(req)
        except Exception:
            parent_ctx = None

        span_name = f"mcp.{method}"
        if tool_name:
            span_name = f"mcp.tools.{tool_name}"

        with tracer.start_as_current_span(span_name, context=parent_ctx) as span:  # type: ignore[attr-defined]
            span.set_attribute("mcp.method", method)
            if tool_name:
                span.set_attribute("mcp.tool", tool_name)
            result = await call_next(context)
            return result


def _is_run_token(s: str) -> bool:
    """Check if string is a valid UUID (run token from Control)."""
    if not s or not isinstance(s, str):
        return False
    try:
        uuid.UUID(s)
        return True
    except (ValueError, TypeError):
        return False


class AuthTokenMiddleware(Middleware):
    """Require Bearer run token (UUID from Control). Use MCP_SKIP_AUTH_FOR_INITIALIZE=1 for local dev only."""

    async def on_request(self, context: MiddlewareContext, call_next):
        req = _request_from_context(context)
        if _is_schema_endpoint(req):
            return await call_next(context)

        token = _extract_token_from_context(context, req)

        if not token:
            skip_for_init = os.getenv("MCP_SKIP_AUTH_FOR_INITIALIZE", "").strip().lower() in ("1", "true", "yes")
            if skip_for_init and getattr(context, "method", None) == "initialize":
                logging.debug(
                    "[AuthToken] MCP_SKIP_AUTH_FOR_INITIALIZE: allowing initialize without token (local dev only)"
                )
            else:
                had_ctx = False
                try:
                    had_ctx = _http_request_ctx.get() is not None
                except LookupError:
                    pass
                logging.warning(
                    "[AuthToken] invalid or missing auth token (method=%s, had_http_request_ctx=%s)",
                    getattr(context, "method", "?"),
                    had_ctx,
                )
                raise PermissionError("invalid or missing auth token")
        elif not _is_run_token(token):
            raise PermissionError("invalid or missing auth token")

        return await call_next(context)


class ControlConfigMiddleware(Middleware):
    def __init__(self, config_schema: Optional[Dict[str, Any]] = None, server_path: str = "/mcp/config") -> None:
        self.config_schema = config_schema or {}
        self.server_path = server_path

    async def on_request(self, context: MiddlewareContext, call_next):
        fast_ctx = getattr(context, "fastmcp_context", None)
        req = _request_from_context(context)
        if _is_schema_endpoint(req):
            return JSONResponse(self.config_schema or {})

        token = _extract_token_from_context(context, req)
        control_base = (os.getenv("MCP_CONTROL_SERVER_URL") or "").strip()
        required = os.getenv("MCP_CONFIG_FETCH_REQUIRED", "true").lower() == "true"

        resolved_config: Dict[str, Any] = {}
        if control_base:
            if not token:
                if required:
                    raise PermissionError("missing auth token for control config resolution")
            else:
                timeout = float(os.getenv("MCP_CONTROL_TIMEOUT_SEC", "5"))
                runtime_context = _build_runtime_context(context, req)
                try:
                    resolved_config = await asyncio.to_thread(
                        _fetch_control_config,
                        control_base,
                        self.server_path,
                        token,
                        self.config_schema,
                        runtime_context,
                        timeout,
                    )
                except Exception as exc:
                    if required:
                        raise PermissionError(f"control config resolution failed: {exc}") from exc

        tokens = set_request_context(token, resolved_config)
        try:
            # Attach onto FastMCP context so user code can access ctx.config directly.
            attach_config_to_ctx(fast_ctx, resolved_config)
            result = await call_next(context)
            return result
        finally:
            reset_request_context(tokens)


# Simple HMAC auth: client sends X-MCP-KeyId, X-MCP-Timestamp, X-MCP-Signature.
# Signature is hex(hmac_sha256(secret, f"{ts}\n{method}\n{path}")) with up to 5 minutes skew.
class HMACAuthMiddleware(Middleware):
    def _load_secret(self, key_id: str) -> Optional[str]:
        # Single key via env
        single_id = os.getenv("MCP_HMAC_KEY_ID")
        single_secret = os.getenv("MCP_HMAC_SECRET")
        if single_id and single_secret and key_id == single_id:
            return single_secret
        # TODO: Optionally support JSON map in MCP_HMAC_KEYS_JSON later
        return None

    async def on_request(self, context: MiddlewareContext, call_next):
        req = None
        try:
            fast_ctx = getattr(context, "fastmcp_context", None)
            if fast_ctx is not None and getattr(fast_ctx, "request_context", None) is not None:
                req = getattr(fast_ctx.request_context, "request", None)
        except Exception:
            req = None
        if _is_schema_endpoint(req):
            return await call_next(context)

        # If HMAC is configured via env, enforce; otherwise allow through
        configured = bool(os.getenv("MCP_HMAC_KEY_ID") and os.getenv("MCP_HMAC_SECRET"))
        if not configured:
            return await call_next(context)

        try:
            fast_ctx = getattr(context, "fastmcp_context", None)
            if fast_ctx is None or getattr(fast_ctx, "request_context", None) is None:
                raise PermissionError("missing request context")
            req = getattr(fast_ctx.request_context, "request", None)
            if req is None:
                raise PermissionError("missing request")

            # Extract headers
            key_id = req.headers.get("X-MCP-KeyId") or req.headers.get("X-MCP-Key")
            ts = req.headers.get("X-MCP-Timestamp")
            sig = req.headers.get("X-MCP-Signature")
            if not key_id or not ts or not sig:
                raise PermissionError("missing hmac headers")

            # Timestamp freshness (skew up to 300s)
            try:
                ts_int = int(ts)
            except Exception:
                raise PermissionError("invalid timestamp")
            now = int(time.time())
            if abs(now - ts_int) > 300:
                raise PermissionError("stale timestamp")

            secret = self._load_secret(key_id)
            if not secret:
                raise PermissionError("unknown key id")

            method = (getattr(req, "method", "POST") or "POST").upper()
            path = getattr(getattr(req, "url", None), "path", "/mcp") or "/mcp"
            base = f"{ts}\n{method}\n{path}"
            expected = hmac.new(secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).hexdigest()

            if not hmac.compare_digest(expected, sig):
                raise PermissionError("invalid signature")

        except PermissionError:
            raise
        except Exception:
            raise PermissionError("hmac verification failed")

        return await call_next(context)


def _extract_request_token(req: Any) -> Optional[str]:
    """Extract bearer token from Authorization header only."""
    if req is None:
        return None

    def _from_headers(target: Any, key: str) -> Optional[str]:
        try:
            hdrs = getattr(target, "headers", None)
            if hdrs is not None and hasattr(hdrs, "get"):
                raw = hdrs.get(key)
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
        except Exception:
            pass
        try:
            if isinstance(target, dict):
                hdrs = target.get("headers")
                if isinstance(hdrs, dict):
                    for hk, hv in hdrs.items():
                        if str(hk).lower() == key.lower() and isinstance(hv, str) and hv.strip():
                            return hv.strip()
        except Exception:
            pass
        return None

    auth = _from_headers(req, "Authorization")
    if auth and isinstance(auth, str) and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        return token if token else None
    return None


def _extract_token_from_context(context: Any, req: Any) -> Optional[str]:
    # Stateless HTTP: request set by patched MiddlewareServerSession before middleware runs.
    try:
        ctx_req = _http_request_ctx.get()
        token = _extract_request_token(ctx_req) if ctx_req is not None else None
        if token:
            return token
    except LookupError:
        pass

    # Primary path: request from FastMCP context.
    token = _extract_request_token(req) if req is not None else None
    if token:
        return token

    # Fallbacks for request placement differences across transports/versions.
    for attr in ("request", "http_request", "raw_request"):
        try:
            cand = getattr(context, attr, None)
        except Exception:
            cand = None
        token = _extract_request_token(cand) if cand is not None else None
        if token:
            return token

    # Some SDK versions keep request-like metadata directly on context objects.
    for carrier in (context, getattr(context, "fastmcp_context", None), getattr(context, "request_context", None)):
        token = _extract_request_token(carrier) if carrier is not None else None
        if token:
            return token

    try:
        request_ctx = getattr(context, "request_context", None)
        cand = getattr(request_ctx, "request", None) if request_ctx is not None else None
        token = _extract_request_token(cand) if cand is not None else None
        if token:
            return token
    except Exception:
        pass

    try:
        fast_ctx = getattr(context, "fastmcp_context", None)
        request_ctx = getattr(fast_ctx, "request_context", None) if fast_ctx is not None else None
        cand = getattr(request_ctx, "request", None) if request_ctx is not None else None
        token = _extract_request_token(cand) if cand is not None else None
        if token:
            return token
    except Exception:
        pass

    # FastMCP-documented fallback for initialize path over HTTP transports.
    try:
        cand = get_http_request()
        token = _extract_request_token(cand) if cand is not None else None
        if token:
            return token
    except Exception:
        pass

    # For initialize: request_ctx is never set (session handles directly).
    # Fall back to FastMCP's _current_http_request (set by RequestContextMiddleware).
    try:
        from fastmcp.server.http import _current_http_request

        cand = _current_http_request.get()
        token = _extract_request_token(cand) if cand is not None else None
        if token:
            return token
    except Exception:
        pass

    return None


def _request_from_context(context: Any) -> Any:
    # Stateless HTTP: request set by patched MiddlewareServerSession before middleware runs.
    try:
        ctx_req = _http_request_ctx.get()
        if ctx_req is not None:
            return ctx_req
    except LookupError:
        pass

    try:
        fast_ctx = getattr(context, "fastmcp_context", None)
        if fast_ctx is not None:
            request_ctx = getattr(fast_ctx, "request_context", None)
            if request_ctx is not None:
                req = getattr(request_ctx, "request", None)
                if req is not None:
                    return req
    except Exception:
        pass

    # RequestResponder path: message_metadata.request_context has the HTTP request
    try:
        msg = getattr(context, "message", None)
        if msg is not None:
            meta = getattr(msg, "message_metadata", None)
            if meta is not None:
                req_cand = getattr(meta, "request_context", None)
                if req_cand is not None:
                    return req_cand
    except Exception:
        pass

    # During initialize, request_context may be unavailable. Use FastMCP helper.
    try:
        return get_http_request()
    except Exception:
        pass

    # For initialize: request_ctx is never set. Fall back to FastMCP's _current_http_request.
    try:
        from fastmcp.server.http import _current_http_request

        return _current_http_request.get()
    except Exception:
        return None


def _fetch_control_config(
    control_base: str,
    server_path: str,
    token: str,
    config_schema: Dict[str, Any],
    runtime_context: Dict[str, Any],
    timeout: float,
) -> Dict[str, Any]:
    url = f"{control_base.rstrip('/')}{server_path}"
    payload = {
        "configSchema": config_schema,
        "config_schema": config_schema,
        "schema": config_schema,
        "runtimeContext": runtime_context,
        "runtime_context": runtime_context,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urlerror.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""
        raise RuntimeError(f"control server returned {exc.code}: {body}") from exc
    except Exception as exc:
        raise RuntimeError(f"control server request failed: {exc}") from exc

    if not raw:
        return {}
    parsed = json.loads(raw)
    if isinstance(parsed, dict):
        if isinstance(parsed.get("config"), dict):
            return parsed["config"]
        if isinstance(parsed.get("data"), dict):
            return parsed["data"]
        return parsed
    raise RuntimeError("invalid control config response")


def _build_runtime_context(context: Any, req: Any) -> Dict[str, Any]:
    """Build minimal runtime context for Control /mcp/config. Sends server_id and tool_name.
    Control resolves tenant_id, user_id, workflow_id, run_id from the Bearer run token."""
    ctx: Dict[str, Any] = {}

    # server_id: prefer MCP_SERVER_ID env (set at deploy), then header/query
    server_id = os.environ.get("MCP_SERVER_ID", "").strip()
    if not server_id and req is not None:
        server_id = _pick_from_req(req, ["X-MCP-Server-Id"], ["server_id"])
    if server_id:
        ctx["server_id"] = server_id

    # tool_name: from context, request headers/query, or JSON-RPC method (e.g. "initialize")
    try:
        tool_name = getattr(getattr(context, "message", None), "name", None)
        if isinstance(tool_name, str) and tool_name.strip():
            ctx["tool_name"] = tool_name.strip()
    except Exception:
        pass
    if "tool_name" not in ctx and req is not None:
        tn = _pick_from_req(req, ["X-Tool-Name", "X-MCP-Tool-Name"], ["tool_name"])
        if tn:
            ctx["tool_name"] = tn
    if "tool_name" not in ctx:
        # Fallback for initialize/list_tools etc.: use __initialize so Control accepts the request
        ctx["tool_name"] = "__initialize"

    return ctx


def _pick_from_req(req: Any, header_names: list[str], query_names: list[str]) -> str:
    """Extract a string value from request headers or query params."""
    for h in header_names:
        try:
            raw = req.headers.get(h)
        except Exception:
            raw = None
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    if hasattr(req, "query_params"):
        for q in query_names:
            try:
                raw = req.query_params.get(q)
            except Exception:
                raw = None
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return ""


def _parse_connection_ids(raw: str) -> list[str]:
    try:
        if raw.startswith("["):
            val = json.loads(raw)
            if isinstance(val, list):
                out = [str(v).strip() for v in val if str(v).strip()]
                return out
    except Exception:
        pass

    out = [p.strip() for p in raw.split(",") if p.strip()]
    return out


def _is_schema_endpoint(req: Any) -> bool:
    if req is None:
        return False
    try:
        method = (getattr(req, "method", "") or "").upper()
        path = getattr(getattr(req, "url", None), "path", "") or ""
        return method == "GET" and path == "/mcp/config/schema"
    except Exception:
        return False


