"""'My KG' through the real proxy: only the owner's own session can read their agent's graph."""
from __future__ import annotations

import httpx
import pytest

from tests.integration.test_registry_live import api, login  # noqa: F401  (fixture + helper)

pytestmark = pytest.mark.live


def graph(live_stack, owner, headers):
    return httpx.get(f"{live_stack}/agent/{owner}/owner/graph", headers=headers, timeout=10)


def test_owner_reads_own_graph(api, live_stack):
    r = graph(live_stack, "persona_a", login(api, "persona_a"))
    assert r.status_code == 200
    body = r.json()
    assert body["owner"] == "persona_a" and len(body["nodes"]) > 20 and body["local_contradictions"]


@pytest.mark.parametrize("viewer", ["persona_b", "persona_c", "persona_d", "persona_e"])
def test_other_sessions_cannot_read_a_graph(api, live_stack, viewer):
    r = graph(live_stack, "persona_a", login(api, viewer))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_the_owner"


def test_graph_requires_a_registry_signed_session(api, live_stack):
    assert graph(live_stack, "persona_a", {}).status_code == 401
    assert graph(live_stack, "persona_a", {"Authorization": "Bearer forged.token.value"}).status_code == 401


@pytest.mark.parametrize("path", ["/agent/persona_a/internal/health", "/agent/persona_a/internal/psi/setup",
                                  "/agent/persona_a/owner/", "/agent/persona_e/owner/graph", "/agent/agent_a/"])
def test_proxy_exposes_nothing_else_on_agents(live_stack, path):
    assert httpx.get(f"{live_stack}{path}", timeout=10).status_code == 404


def test_registry_never_serves_graphs(api):
    h = login(api, "persona_a")
    for path in ("/v1/graph", "/v1/researchers/persona_a/graph", "/internal/graph"):
        assert api.get(path, headers=h).status_code == 404
