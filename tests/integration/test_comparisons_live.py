"""Phase 4 gate on the real stack: agent-to-agent PSI-CA, exact ground truth, release gating, leak scan."""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import time
import uuid
from itertools import combinations

import httpx
import pytest

from fkg_protocol.results import band
from tests.conftest import AGENT_SERVICES, DATA, GRAPH_PERSONAS, compose
from tests.integration.test_registry_live import api, login  # noqa: F401  (fixture + helper)

pytestmark = pytest.mark.live
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "EXPIRED", "APPROVED"}


def scope(topics, disclosure="summary", classes=("Protein", "Interaction")):
    return {"topics": topics, "entity_classes": list(classes), "metric": "jaccard", "protocol": "psi_ca",
            "disclosure": disclosure}


def wait(api, rid, headers, timeout=45.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        got = api.get(f"/v1/requests/{rid}", headers=headers).json()
        if got["status"] in TERMINAL and got["status"] != "RUNNING":
            return got
        time.sleep(0.3)
    raise AssertionError(f"request {rid} still running")


def agent_log(persona: str) -> list[dict]:
    out = compose("exec", "-T", AGENT_SERVICES[persona], "sh", "-c",
                  "cat /var/lib/fkg/comparisons.jsonl 2>/dev/null || true").stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def run_targeted(api, requester, recipient, topics, visibility="both", disclosure="summary"):
    req_h, rec_h = login(api, requester), login(api, recipient)
    r = api.post(f"/v1/researchers/{recipient}/requests", headers=req_h,
                 json={"scope": scope(topics, disclosure), "result_visibility": visibility,
                       "idempotency_key": uuid.uuid4().hex})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert api.post(f"/v1/requests/{rid}/approve", headers=rec_h).status_code == 200
    assert api.post(f"/v1/requests/{rid}/run", headers=req_h).status_code == 202
    return rid, wait(api, rid, req_h)


@pytest.fixture(scope="module")
def all_pairs(live_stack, ground_truth):
    """Run every fixture pair once through the full workflow (results shared by several tests)."""
    with httpx.Client(base_url=f"{live_stack}/api", timeout=60) as c:
        c.post("/v1/test/reset")
        for svc in AGENT_SERVICES.values():
            compose("exec", "-T", svc, "sh", "-c", "rm -f /var/lib/fkg/comparisons.jsonl /var/lib/fkg/agent_state.json "
                    "/tmp/fkg-capture/payloads.log")
        runs = {}
        for a, b in combinations(GRAPH_PERSONAS, 2):
            topic = ground_truth["topic_similarity"][f"{a}|{b}"]["matched_topics"][0]
            rid, final = run_targeted(c, a, b, [topic])
            results = {p: c.get(f"/v1/requests/{rid}/result", headers=login(c, p)).json() for p in (a, b)}
            runs[(a, b)] = {"request_id": rid, "final": final, "results": results}
        yield runs
        c.post("/v1/test/reset")


def test_every_pair_completes_with_psi_ca(all_pairs):
    for (a, b), run in all_pairs.items():
        assert run["final"]["status"] == "COMPLETED", (a, b, run["final"])
        for p in (a, b):
            assert run["results"][p]["method"] == "psi_ca/openmined-ecdh/2.0.6"
            assert run["results"][p]["producer_id"] == p


def test_exact_psi_ca_counts_equal_ground_truth(all_pairs, ground_truth):
    """The output agents' private logs hold exact counts; they must equal the plaintext ground truth."""
    for (a, b), run in all_pairs.items():
        key = f"{a}|{b}"
        for me, other in ((a, b), (b, a)):
            (entry,) = [e for e in agent_log(me) if e["request_id"] == run["request_id"]]
            prot, inter = entry["exact"]["Protein"], entry["exact"]["Interaction"]
            gt_p, gt_i = ground_truth["protein_overlap"][key], ground_truth["interaction_overlap"][key]
            assert prot["intersection"] == gt_p["intersection"], (key, me)
            assert prot["own_size"] + prot["other_size"] - prot["intersection"] == gt_p["union"], (key, me)
            assert inter["intersection"] == gt_i["intersection"], (key, me)
            assert inter["own_size"] + inter["other_size"] - inter["intersection"] == gt_i["union"], (key, me)


def test_released_bands_match_ground_truth(all_pairs, ground_truth):
    for (a, b), run in all_pairs.items():
        key = f"{a}|{b}"
        for cls, gt_key in (("Protein", "protein_overlap"), ("Interaction", "interaction_overlap")):
            gt = ground_truth[gt_key][key]
            expected = band("jaccard", gt["intersection"], gt["union"])
            for p in (a, b):
                assert run["results"][p]["results"][cls]["band"] == expected, (key, p, cls)
    # Low-count pair is suppressed rather than scored.
    assert all_pairs[("persona_a", "persona_d")]["results"]["persona_a"]["results"]["Protein"]["band"] \
        == "insufficient_disclosure"


def test_released_results_contain_no_numbers_or_identifiers(all_pairs):
    for run in all_pairs.values():
        for res in run["results"].values():
            text = json.dumps(res["results"])
            assert not any(ch.isdigit() for ch in text.replace("10-24", "").replace("1-9", "")
                           .replace("25-49", "").replace("50+", ""))


# ---- leak scan --------------------------------------------------------------------------------------

def _private_needles() -> list[str]:
    """Every private identifier of every graph, plus hashed and encoded forms."""
    from agents.common.app.graph import eligible_sets, load_private_graph
    import tempfile
    from pathlib import Path
    ids: set[str] = set()
    for p in GRAPH_PERSONAS:
        with tempfile.TemporaryDirectory() as tmp:
            g = load_private_graph(p, DATA / "private" / f"{p}.ttl", Path(tmp))
            for s in eligible_sets(g, ["Protein", "Interaction"]).values():
                ids |= s
    needles = set(ids)
    for i in ids:
        needles.add(hashlib.sha256(i.encode()).hexdigest())
        needles.add(base64.b64encode(i.encode()).decode().rstrip("="))
    return sorted(needles)


def test_no_private_identifier_leaves_any_agent(all_pairs):
    needles = [n.encode() for n in _private_needles()]
    corpus: dict[str, bytes] = {}
    for svc in AGENT_SERVICES.values():
        corpus[f"{svc}:capture"] = compose("exec", "-T", svc, "sh", "-c",
                                           "cat /tmp/fkg-capture/payloads.log 2>/dev/null || true").stdout.encode()
        corpus[f"{svc}:exact-log"] = compose("exec", "-T", svc, "sh", "-c",
                                             "cat /var/lib/fkg/comparisons.jsonl 2>/dev/null || true").stdout.encode()
    corpus["registry-db"] = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "pg_dump", "-U", "fkg_registry", "fkg_registry"],
        capture_output=True, check=True).stdout
    corpus["all-logs"] = subprocess.run(["docker", "compose", "logs", "--no-color"], capture_output=True).stdout

    # The scan must not be vacuous: PSI messages were captured on every agent.
    for svc in AGENT_SERVICES.values():
        assert b"/internal/psi/setup" in corpus[f"{svc}:capture"], svc
    assert b"comparison_results" in corpus["registry-db"]

    hits = [(where, n.decode()) for where, blob in corpus.items() for n in needles if n in blob]
    assert hits == [], hits[:10]


# ---- release gating on the real stack ----------------------------------------------------------------

def test_policy_tightening_during_compute_prevents_release(api):
    a = login(api, "persona_a")
    ch = api.post("/v1/channels", headers=a, json={"topics": ["proteomics", "mass_spectrometry"]}).json()
    api.post(f"/v1/channels/{ch['id']}/activate", headers=a)
    b = login(api, "persona_b")
    rid = api.post(f"/v1/channels/{ch['id']}/requests", headers=b,
                   json={"scope": scope(["mass_spectrometry"], "score_only"), "result_visibility": "requester_only",
                         "idempotency_key": uuid.uuid4().hex}).json()["id"]
    api.post(f"/v1/requests/{rid}/approve", headers=a)
    api.post("/v1/test/agent-delay", json={"seconds": 3})
    assert api.post(f"/v1/requests/{rid}/run", headers=b).status_code == 202
    time.sleep(1)
    assert api.get(f"/v1/requests/{rid}", headers=b).json()["status"] == "RUNNING"
    r = api.patch(f"/v1/channels/{ch['id']}", headers=a, json={"topics": ["proteomics"], "expected_policy_version": 1})
    assert r.status_code == 200
    final = wait(api, rid, b)
    assert (final["status"], final["status_reason"]) == ("CANCELLED", "policy_incompatible")
    assert api.get(f"/v1/requests/{rid}/result", headers=b).status_code == 409
    assert not [e for e in agent_log("persona_b") if e["request_id"] == rid]  # nothing kept after revocation
    api.post("/v1/test/agent-delay", json={"seconds": 0})


def test_expired_channel_cancels_comparison(api):
    a = login(api, "persona_a")
    ch = api.post("/v1/channels", headers=a, json={"topics": ["proteomics"]}).json()
    api.post(f"/v1/channels/{ch['id']}/activate", headers=a)
    b = login(api, "persona_b")
    rid = api.post(f"/v1/channels/{ch['id']}/requests", headers=b,
                   json={"scope": scope(["proteomics"], "score_only"), "idempotency_key": uuid.uuid4().hex}).json()["id"]
    api.post(f"/v1/requests/{rid}/approve", headers=a)
    api.post("/v1/test/clock/advance", json={"seconds": 24 * 3600})
    b = login(api, "persona_b")
    r = api.post(f"/v1/requests/{rid}/run", headers=b)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "request_expired"


def test_demo_reset_clears_agent_local_state(api):
    rid, final = run_targeted(api, "persona_c", "persona_d", ["interactomics"])
    assert final["status"] == "COMPLETED" and agent_log("persona_c")
    r = api.post("/v1/test/reset").json()
    assert r["agents_reset"] == {p: 200 for p in GRAPH_PERSONAS}
    for p in GRAPH_PERSONAS:
        assert agent_log(p) == []
        state = compose("exec", "-T", AGENT_SERVICES[p], "sh", "-c",
                        "cat /var/lib/fkg/agent_state.json 2>/dev/null || echo none").stdout.strip()
        assert state == "none", p


# ---- service authentication on the real network -----------------------------------------------------

_PROBE = r"""
import json, sys, time, httpx
sys.path.insert(0, "/app")
from fkg_protocol.keys import load_private
from fkg_protocol.tokens import sign_service_token
me, target, path, mode = sys.argv[1:5]
key = load_private(__import__("pathlib").Path("/keys/private/private.pem"))
body = json.dumps({"ticket": "x", "consumer_id": me, "entity_class": "Protein", "client_size": 5}).encode()
tok = sign_service_token(key, me, target, "POST", path, body, time.time())
url = f"http://{ {'persona_a':'agent_a','persona_b':'agent_b','persona_c':'agent_c','persona_d':'agent_d','registry':'registry'}[target] }:8000{path}"
send = body if mode != "tamper" else body.replace(b'"x"', b'"y"')
codes = []
for _ in range(2 if mode == "replay" else 1):
    r = httpx.post(url, content=send, headers={"X-Service-Token": tok if mode != "none" else "", "Content-Type": "application/json"})
    codes.append([r.status_code, r.json().get("detail", {}).get("code") if r.headers.get("content-type","").startswith("application/json") else None])
print(json.dumps(codes))
"""


def probe(from_service: str, me: str, target: str, path: str, mode: str = "ok") -> list:
    out = compose("exec", "-T", from_service, "python", "-c", _PROBE, me, target, path, mode).stdout
    return json.loads(out.strip().splitlines()[-1])


def test_peer_endpoint_rejects_unauthenticated_tampered_and_replayed(live_stack):
    assert probe("agent_b", "persona_b", "persona_a", "/internal/psi/setup", "none")[0] == [401, "missing_service_token"]
    assert probe("agent_b", "persona_b", "persona_a", "/internal/psi/setup", "tamper")[0] == [401, "body_hash_mismatch"]
    first, second = probe("agent_b", "persona_b", "persona_a", "/internal/psi/setup", "replay")
    assert first == [403, "invalid_ticket"]                    # authenticated, but the ticket is junk
    assert second == [401, "replayed_service_token"]


def test_agents_cannot_impersonate_registry_and_registry_cannot_join_psi(live_stack):
    # An agent calling the registry-only run endpoint is refused.
    assert probe("agent_b", "persona_b", "persona_a", "/internal/comparisons/run")[0][0] == 401
    # The registry is not on the peer network and is not an allowed PSI issuer.
    code = ("import httpx\ntry:\n print(httpx.post('http://agent_a:8000/internal/psi/setup', json={}).status_code)\n"
            "except Exception as e: print('unreachable')")
    assert compose("exec", "-T", "registry", "python", "-c", code).stdout.strip() == "401"


def test_evidence_export_is_always_denied(live_stack):
    code = probe("agent_c", "persona_c", "persona_d", "/internal/evidence/export")
    assert code[0] == [403, "evidence_export_disabled_v1"]


def test_each_service_holds_only_its_own_private_key(live_stack):
    for svc in ["registry", *AGENT_SERVICES.values()]:
        listing = compose("exec", "-T", svc, "sh", "-c", "ls /keys/private /keys/public").stdout
        assert listing.count("private.pem") == 1, svc
        assert "persona_" in listing and "registry.pem" in listing  # public keyring present
