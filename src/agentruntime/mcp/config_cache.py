"""In-process MCP config cache, singleflight, and 429 retry — mirrors agentruntime-mcp-go."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional

from .errors import ControlError

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_CACHE_TTL_SEC = 60
DEFAULT_CONFIG_RETRY_BUDGET_SEC = 30
MIN_CONFIG_CACHE_TTL_SEC = 30
MAX_CONFIG_CACHE_TTL_SEC = 120
DEFAULT_RATE_LIMIT_WAIT_SEC = 5
RATE_LIMIT_WAIT_LOG_THRESHOLD_SEC = 2.0

FetchFn = Callable[
    [str, str, Mapping[str, Any], Mapping[str, Any], float],
    Dict[str, Any],
]


@dataclass
class _InflightSlot:
    event: threading.Event = field(default_factory=threading.Event)
    result: Optional[Dict[str, Any]] = None
    error: Optional[BaseException] = None


_cache_lock = threading.RLock()
_cache: Dict[str, tuple[Dict[str, Any], float]] = {}
_inflight: Dict[str, _InflightSlot] = {}


def fetch_control_config_cached(
    control_base: str,
    token: str,
    config_schema: Mapping[str, Any],
    runtime_context: Mapping[str, Any],
    timeout: float,
    fetch_fn: FetchFn,
) -> Dict[str, Any]:
    if not token:
        return fetch_control_config_with_retry(
            control_base, token, config_schema, runtime_context, timeout, fetch_fn
        )

    key = config_cache_key(token, config_schema, runtime_context)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    leader = False
    with _cache_lock:
        cached = _cache_get_unlocked(key)
        if cached is not None:
            return cached
        slot = _inflight.get(key)
        if slot is None:
            slot = _InflightSlot()
            _inflight[key] = slot
            leader = True

    if leader:
        try:
            cfg = fetch_control_config_with_retry(
                control_base, token, config_schema, runtime_context, timeout, fetch_fn
            )
            put_config_cache_entry(key, cfg)
            slot.result = cfg
        except BaseException as exc:
            slot.error = exc
        finally:
            slot.event.set()
            with _cache_lock:
                _inflight.pop(key, None)
    else:
        slot.event.wait()

    if slot.error is not None:
        raise slot.error
    return dict(slot.result or {})


def fetch_control_config_with_retry(
    control_base: str,
    token: str,
    config_schema: Mapping[str, Any],
    runtime_context: Mapping[str, Any],
    timeout: float,
    fetch_fn: FetchFn,
) -> Dict[str, Any]:
    deadline = time.monotonic() + config_retry_budget_sec()
    attempt = 0
    while True:
        try:
            return fetch_fn(control_base, token, config_schema, runtime_context, timeout)
        except ControlError as exc:
            if exc.status != 429:
                raise
            wait = rate_limit_wait_seconds(exc, attempt)
            if wait <= 0:
                raise
            if time.monotonic() + wait > deadline:
                logger.warning(
                    "mcp control config: rate limit retry budget exhausted after %d attempt(s)",
                    attempt + 1,
                )
                raise
            if wait >= RATE_LIMIT_WAIT_LOG_THRESHOLD_SEC:
                logger.warning(
                    "mcp control config: rate limited (capacity), waiting %.1fs before retry (attempt %d)",
                    wait,
                    attempt + 1,
                )
            time.sleep(wait)
            attempt += 1


def rate_limit_wait_seconds(exc: ControlError, attempt: int) -> float:
    sec = exc.retry_after_sec or retry_after_from_control_body(exc.body)
    if sec <= 0:
        sec = DEFAULT_RATE_LIMIT_WAIT_SEC
    sec = max(1, min(int(sec), 60))
    if attempt > 0 and not exc.retry_after_sec and retry_after_from_control_body(exc.body) <= 0:
        sec = min(sec * (2**attempt), 60)
    return float(sec)


def retry_after_from_control_body(body: str) -> int:
    body = (body or "").strip()
    if not body:
        return 0
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return 0
    if not isinstance(parsed, dict):
        return 0
    top = parsed.get("retry_after")
    if isinstance(top, int) and top > 0:
        return top
    details = parsed.get("details")
    if isinstance(details, dict):
        ra = details.get("retry_after")
        if isinstance(ra, int) and ra > 0:
            return ra
    return 0


def config_cache_key(
    token: str, config_schema: Mapping[str, Any], runtime_context: Mapping[str, Any]
) -> str:
    return "|".join(
        [
            token_fingerprint(token),
            runtime_context_instance_key(runtime_context),
            config_schema_hash(config_schema),
        ]
    )


def token_fingerprint(token: str) -> str:
    digest = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
    return digest[:16]


def runtime_context_instance_key(runtime_context: Mapping[str, Any]) -> str:
    inst = str(runtime_context.get("instance_id") or "").strip()
    if inst:
        return inst
    sid = str(runtime_context.get("server_id") or "").strip()
    if sid:
        return f"server:{sid}"
    return ""


def config_schema_hash(config_schema: Mapping[str, Any]) -> str:
    if not config_schema:
        return "empty"
    try:
        raw = json.dumps(config_schema, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except TypeError:
        return "marshal-error"
    return hashlib.sha256(raw).hexdigest()[:16]


def config_cache_ttl_sec() -> int:
    sec = DEFAULT_CONFIG_CACHE_TTL_SEC
    raw = os.getenv("MCP_CONFIG_CACHE_TTL_SEC", "").strip()
    if raw:
        try:
            sec = int(raw)
        except ValueError:
            pass
    return max(MIN_CONFIG_CACHE_TTL_SEC, min(sec, MAX_CONFIG_CACHE_TTL_SEC))


def config_retry_budget_sec() -> float:
    sec = DEFAULT_CONFIG_RETRY_BUDGET_SEC
    raw = os.getenv("MCP_CONFIG_RETRY_BUDGET_SEC", "").strip()
    if raw:
        try:
            n = int(raw)
            if n > 0:
                sec = n
        except ValueError:
            pass
    return float(sec)


def put_config_cache_entry(key: str, cfg: Dict[str, Any]) -> None:
    expires = time.monotonic() + config_cache_ttl_sec()
    with _cache_lock:
        _cache[key] = (dict(cfg), expires)


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    with _cache_lock:
        return _cache_get_unlocked(key)


def _cache_get_unlocked(key: str) -> Optional[Dict[str, Any]]:
    ent = _cache.get(key)
    if ent is None:
        return None
    if time.monotonic() >= ent[1]:
        _cache.pop(key, None)
        return None
    return dict(ent[0])


def reset_config_cache_for_test() -> None:
    with _cache_lock:
        _cache.clear()
        _inflight.clear()
