"""Phase 1 gate: the registry cannot read any private graph, statically or at runtime."""
from __future__ import annotations

import json
import subprocess

import pytest

from tests.conftest import AGENT_SERVICES, DATA, GRAPH_PERSONAS, ROOT, compose

AGENTS = set(AGENT_SERVICES.values())


# ---- static: compose topology -------------------------------------------------------------

def _mounts(svc: dict) -> dict[str, dict]:
    return {v.get("source", ""): v for v in svc.get("volumes", [])}


def test_registry_mounts_only_its_key_and_public_keyring(compose_config):
    reg = compose_config["services"]["registry"]
    mounts = _mounts(reg)
    assert set(mounts) == {"keys_registry", "keys_public"}, "registry must not mount graphs or agent keys"
    assert all(m.get("read_only") for m in mounts.values())
    assert not any(k.startswith("AGENT_ID") or k == "GRAPH_FIXTURE" for k in reg.get("environment", {}))


def test_private_keys_are_never_shared(compose_config):
    owners = {"keys_registry": "registry", **{f"keys_{p}": AGENT_SERVICES[p] for p in GRAPH_PERSONAS}}
    for name, svc in compose_config["services"].items():
        if name == "keygen":
            assert svc.get("network_mode") == "none"  # provisioning container has no network at all
            continue
        for source in _mounts(svc):
            if source in owners:
                assert owners[source] == name, f"{name} mounts {source}"


def test_registry_is_not_on_peer_network(compose_config):
    assert "peer" not in compose_config["services"]["registry"]["networks"]
    for agent in AGENTS:
        assert "peer" in compose_config["services"][agent]["networks"]


def test_internal_networks_are_internal(compose_config):
    for net in ("data", "agents", "peer"):
        assert compose_config["networks"][net].get("internal") is True, net


def test_only_frontend_publishes_host_ports(compose_config):
    published = {name for name, svc in compose_config["services"].items() if svc.get("ports")}
    assert published == {"frontend"}


def test_each_agent_mounts_only_its_own_graph(compose_config):
    for persona, service in AGENT_SERVICES.items():
        sources = [v.get("source", "") for v in compose_config["services"][service]["volumes"]]
        binds = [s for s in sources if s.endswith(".ttl")]
        assert len(binds) == 1 and binds[0].replace("\\", "/").endswith(f"private/{persona}.ttl")
        assert f"kg_{persona}" in sources
        others = [p for p in GRAPH_PERSONAS if p != persona]
        assert not any(o in s for s in sources for o in others)


def test_private_fixtures_excluded_from_every_build_context():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "data/synthetic/private" in ignored
    assert "data/synthetic/ground_truth.json" in ignored


# ---- live: running containers ----------------------------------------------------------------

def _exec(service: str, code: str) -> str:
    return compose("exec", "-T", service, "python", "-c", code).stdout


_SCAN = """
import os, json
hits = []
for root in ('/app', '/fixtures', '/var/lib/fkg', '/tmp', '/home'):
    for d, _, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            if f.endswith('.ttl') or f == 'ground_truth.json':
                hits.append(p)
            try:
                data = open(p, 'rb').read()
            except Exception:
                continue
            hits += [p + ':' + n for n in NEEDLES if n.encode() in data]
print(json.dumps(hits))
"""


def _scan(service: str, needles: list[str]) -> list[str]:
    code = _SCAN.replace("NEEDLES", json.dumps(needles))
    return json.loads(_exec(service, code))


@pytest.mark.live
def test_registry_container_holds_no_private_data(live_stack, ground_truth):
    needles = list(ground_truth["canaries"].values())
    assert _scan("registry", needles) == []


@pytest.mark.live
def test_each_agent_holds_only_its_own_graph(live_stack, ground_truth):
    for persona, service in AGENT_SERVICES.items():
        others = [c for p, c in ground_truth["canaries"].items() if p != persona]
        hits = _scan(service, others)
        # Its own fixture mount and store copy are the only .ttl files allowed.
        assert sorted(hits) == ["/fixtures/graph.ttl", "/var/lib/fkg/graph.ttl"], (service, hits)


@pytest.mark.live
def test_agents_expose_nothing_but_health_to_the_registry(live_stack):
    paths = ["/internal/graph", "/graph", "/internal/export", "/docs", "/openapi.json", "/"]
    code = ("import httpx, json; print(json.dumps([httpx.get(f'http://{a}:8000{p}').status_code "
            f"for a in {sorted(AGENTS)!r} for p in {paths!r}]))")
    assert set(json.loads(_exec("registry", code))) == {404}


@pytest.mark.live
def test_agents_have_no_route_to_the_registry_database(live_stack):
    code = ("import socket\ntry:\n socket.create_connection(('postgres', 5432), timeout=2); print('reachable')\n"
            "except Exception: print('unreachable')")
    for service in AGENT_SERVICES.values():
        assert _exec(service, code).strip() == "unreachable", service


@pytest.mark.live
def test_running_registry_is_not_attached_to_peer_network(live_stack):
    container = compose("ps", "-q", "registry").stdout.strip()
    inspect = subprocess.run(["docker", "inspect", container], capture_output=True, text=True, check=True)
    networks = json.loads(inspect.stdout)[0]["NetworkSettings"]["Networks"]
    assert not any(n.endswith("_peer") for n in networks), list(networks)
