"""Mode B signed ingress — mirror agentruntime-mcp-go webhook.go."""

from __future__ import annotations

import hmac
import hashlib
import time
from dataclasses import dataclass
from typing import Union

import httpx

Body = Union[bytes, bytearray]


def sign_mode_b(signing_secret: str, body: Body, unix: int) -> str:
    mac = hmac.new(signing_secret.encode("utf-8"), digestmod=hashlib.sha256)
    mac.update(f"{unix}.".encode("utf-8"))
    mac.update(body)
    return f"t={unix},v1={mac.hexdigest()}"


@dataclass
class ModeBRequest:
    bff_base_url: str
    subscription_id: str
    signing_secret: str
    idempotency_key: str
    body: Body
    content_type: str = "application/json"


def deliver_mode_b(req: ModeBRequest) -> httpx.Response:
    if not (req.bff_base_url and req.subscription_id and req.signing_secret and req.idempotency_key):
        raise ValueError(
            "agentruntime-mcp deliver_mode_b: bff_base_url, subscription_id, signing_secret, "
            "and idempotency_key are required"
        )
    ct = req.content_type.strip() or "application/json"
    unix = int(time.time())
    sig = sign_mode_b(req.signing_secret, req.body, unix)
    url = f"{req.bff_base_url.rstrip('/')}/v1/inbound-webhooks/{req.subscription_id}"
    with httpx.Client(timeout=30.0) as client:
        return client.post(
            url,
            content=bytes(req.body),
            headers={
                "Content-Type": ct,
                "Idempotency-Key": req.idempotency_key,
                "X-Agentruntime-Signature": sig,
            },
        )
