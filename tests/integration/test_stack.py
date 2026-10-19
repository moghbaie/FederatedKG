"""Phase 1 gate: all services healthy, health page served, PSI-CA library usable in agents."""
from __future__ import annotations

import json

import httpx
import pytest

from tests.conftest import AGENT_SERVICES, compose

pytestmark = pytest.mark.live


def test_system_health_all_green(live_stack):
    body = httpx.get(f"{live_stack}/api/v1/system/health", timeout=10).json()
    assert body["status"] == "ok", body
    assert body["registry"]["database"] is True
    assert set(body["agents"]) == set(AGENT_SERVICES)
    for agent in body["agents"].values():
        assert agent == {"status": "ok", "graph_loaded": True}


def test_health_endpoints_leak_no_private_content(live_stack, ground_truth):
    text = httpx.get(f"{live_stack}/api/v1/system/health", timeout=10).text
    text += httpx.get(f"{live_stack}/api/v1/public/personas", timeout=10).text
    for canary in ground_truth["canaries"].values():
        assert canary not in text
    for topics in ground_truth["private_topics"].values():
        assert not any(t in text for t in topics)


def test_health_page_and_banner_served(live_stack):
    html = httpx.get(live_stack, timeout=10).text
    assert '<div id="root">' in html
    personas = httpx.get(f"{live_stack}/api/v1/public/personas", timeout=10).json()
    assert personas["banner"].startswith("Simulated researchers and synthetic knowledge graphs")
    assert [p["researcher_id"] for p in personas["personas"]] == [
        "persona_a", "persona_b", "persona_c", "persona_d", "persona_e"]


@pytest.mark.parametrize("service", sorted(AGENT_SERVICES.values()))
def test_psi_ca_smoke_in_agent_image(live_stack, service):
    out = compose("exec", "-T", service, "python", "-m", "similarity.psi_ca.smoke").stdout
    report = json.loads(out.strip().splitlines()[-1])
    assert report["protocol"] == "psi_ca/openmined-ecdh/2.0.6"
    for r in report["results"]:
        assert r["cardinality"] == r["expected"], r
        assert r["plaintext_on_wire"] is False, r
