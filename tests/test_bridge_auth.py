from __future__ import annotations

import pytest

from agentruntime.mcp.bridge_auth import (
    apply_auth_mapping,
    apply_bridge_headers,
    apply_header_mappings,
)


def test_apply_auth_mapping_bearer() -> None:
    h = apply_auth_mapping({"access_token": "tok123"}, {"type": "bearer", "from": "access_token"})
    assert h["Authorization"] == "Bearer tok123"


def test_apply_auth_mapping_none() -> None:
    assert apply_auth_mapping({}, {"type": "none"}) == {}


def test_apply_header_mappings_grafana() -> None:
    h = apply_header_mappings(
        {
            "grafana_url": "https://acme.grafana.net",
            "service_account_token": "glsa_xxx",
        },
        [
            {"name": "X-Grafana-URL", "from": "grafana_url"},
            {"name": "X-Grafana-Service-Account-Token", "from": "service_account_token"},
        ],
    )
    assert h["X-Grafana-URL"] == "https://acme.grafana.net"
    assert h["X-Grafana-Service-Account-Token"] == "glsa_xxx"


def test_apply_header_mappings_missing_key() -> None:
    with pytest.raises(ValueError, match="grafana_url"):
        apply_header_mappings({}, [{"name": "X-Grafana-URL", "from": "grafana_url"}])


def test_apply_bridge_headers_combined() -> None:
    h = apply_bridge_headers(
        {
            "grafana_url": "https://acme.grafana.net",
            "service_account_token": "glsa_xxx",
        },
        {
            "auth_mapping": {"type": "none"},
            "header_mappings": [
                {"name": "X-Grafana-URL", "from": "grafana_url"},
                {"name": "X-Grafana-Service-Account-Token", "from": "service_account_token"},
            ],
        },
    )
    assert h["X-Grafana-URL"] == "https://acme.grafana.net"


def test_apply_bridge_headers_legacy_auth_only() -> None:
    h = apply_bridge_headers(
        {"access_token": "tok"},
        {"auth_mapping": {"type": "bearer", "from": "access_token"}},
    )
    assert h["Authorization"] == "Bearer tok"
