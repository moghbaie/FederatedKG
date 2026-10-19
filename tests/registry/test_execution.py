"""Phase 4 registry logic with simulated agents: tickets, release gating, package checks, revocation.

A mock transport stands in for the agents (verifying the registry's service token and ticket like a
real agent would). Real agent-to-agent PSI-CA is covered by the live tests.
"""
from __future__ import annotations

import json
import uuid

import httpx
import pytest

from agents.common.app.graph import eligible_sets, load_private_graph
from fkg_protocol.keys import Keyring, generate, load_private
from fkg_protocol.results import shape, sign_package
from fkg_protocol.tickets import counterpart, verify_ticket
from fkg_protocol.tokens import ReplayCache, sign_service_token, verify_service_token
from registry.app.models import AuditEvent, ComparisonResult, Ticket
from registry.app.requests import revalidate_open_requests
from tests.conftest import DATA, GRAPH_PERSONAS
from tests.registry.conftest import make_client

URLS = {p: f"http://{p}.agents" for p in GRAPH_PERSONAS}


class FakeAgents:
    """Behaves like the agents' /internal/comparisons/run, computing in plaintext on fixture graphs."""

    def __init__(self, key_root, graphs_root):
        self.keys = {p: load_private(key_root / p / "private.pem") for p in GRAPH_PERSONAS}
        self.keyring = Keyring.from_dir(key_root / "public")
        self.replay = ReplayCache()
        self.sets = {p: eligible_sets(load_private_graph(p, DATA / "private" / f"{p}.ttl", graphs_root / p),
                                      ["Protein", "Interaction"]) for p in GRAPH_PERSONAS}
        self.mode = "ok"
        self.during_compute = None  # callable(request_id) simulating a concurrent owner action
        self.calls: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        persona = request.url.host.split(".")[0]
        token = request.headers["X-Service-Token"]
        # Verify like a real agent; "now" is the token's own iat because the registry clock may be offset.
        verify_service_token(token, self.keyring, persona, request.method, request.url.path, request.content,
                             self.replay, _ticket_time(token), ("registry",))
        body = json.loads(request.content or b"{}")
        if request.url.path == "/internal/test/clock":
            return httpx.Response(200, json={"ok": True})
        ticket = verify_ticket(body["ticket"], self.keyring.get("registry"), _ticket_time(body["ticket"]))
        self.calls.append({"persona": persona, "ticket": ticket, "consumer": body["consumer_id"]})
        if self.mode.startswith("error:"):
            return httpx.Response(409, json={"detail": {"code": self.mode.split(":", 1)[1]}})
        if self.during_compute:
            self.during_compute(ticket["request_id"])
        peer = counterpart(ticket, persona)
        results = {}
        for cls in ticket["scope"]["entity_classes"]:
            mine, theirs = self.sets[persona][cls], self.sets[peer][cls]
            results[cls] = shape(ticket["scope"]["disclosure"], ticket["scope"]["metric"], len(mine & theirs),
                                 len(mine), len(theirs))
        if self.mode == "numeric":
            results["Protein"]["intersection"] = 12
        pkg = {"request_id": ticket["request_id"], "ticket_id": ticket["jti"], "producer_id": persona,
               "consumer_id": persona, "counterpart_id": peer, "scope": ticket["scope"],
               "policy_version": ticket["policy_version"], "method": "psi_ca/simulated", "algorithm_version": "t",
               "input_provenance": {"graph": f"urn:fkg:graph:{persona}"}, "created_at": "t", "results": results,
               "disclosed_to_counterpart": {"own_set_size": "exact"}}
        if self.mode == "extra_field":
            pkg["matched_ids"] = sorted(self.sets[persona]["Protein"])[:3]
        signer = self.keys[peer] if self.mode == "wrong_key" else self.keys[persona]
        return httpx.Response(200, json={"package": sign_package(signer, pkg)})


def _ticket_time(raw: str) -> float:
    import jwt
    return jwt.decode(raw, options={"verify_signature": False})["iat"]


@pytest.fixture
def env(tmp_path):
    key_root = tmp_path / "keys"
    generate({s: key_root / s for s in ("registry", *GRAPH_PERSONAS)}, key_root / "public")
    agents = FakeAgents(key_root, tmp_path / "graphs")
    client = make_client(tmp_path, agent_urls=URLS, private_key_path=key_root / "registry" / "private.pem",
                         keyring_dir=key_root / "public")
    with client as c:
        c.app.state.agent_transport = httpx.MockTransport(agents)
        yield c, agents


def login(c, persona):
    tok = c.post("/v1/auth/demo-login", json={"researcher_id": persona}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def scope(**over):
    return {"topics": ["interactomics"], "entity_classes": ["Protein", "Interaction"], "metric": "jaccard",
            "protocol": "psi_ca", "disclosure": "summary", **over}


def approved_targeted(c, requester="persona_c", recipient="persona_d", visibility="both", **scope_over):
    r = c.post(f"/v1/researchers/{recipient}/requests", headers=login(c, requester),
               json={"scope": scope(**scope_over), "result_visibility": visibility,
                     "idempotency_key": uuid.uuid4().hex})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert c.post(f"/v1/requests/{rid}/approve", headers=login(c, recipient)).status_code == 200
    return rid


def approved_channel_request(c, topics=("proteomics", "mass_spectrometry"), ask=("mass_spectrometry",)):
    a = login(c, "persona_a")
    ch = c.post("/v1/channels", headers=a, json={"topics": list(topics)}).json()
    c.post(f"/v1/channels/{ch['id']}/activate", headers=a)
    r = c.post(f"/v1/channels/{ch['id']}/requests", headers=login(c, "persona_b"),
               json={"scope": scope(topics=list(ask), disclosure="score_only"), "result_visibility": "both",
                     "idempotency_key": uuid.uuid4().hex})
    rid = r.json()["id"]
    c.post(f"/v1/requests/{rid}/approve", headers=a)
    return ch["id"], rid


# ---- happy path -----------------------------------------------------------------------------------

def test_run_releases_signed_results_to_both_parties(env, ground_truth):
    c, agents = env
    rid = approved_targeted(c)
    r = c.post(f"/v1/requests/{rid}/run", headers=login(c, "persona_c"))
    assert r.status_code == 202
    assert c.get(f"/v1/requests/{rid}", headers=login(c, "persona_c")).json()["status"] == "COMPLETED"
    assert sorted(call["consumer"] for call in agents.calls) == ["persona_c", "persona_d"]
    for p in ("persona_c", "persona_d"):
        res = c.get(f"/v1/requests/{rid}/result", headers=login(c, p)).json()
        assert res["results"]["Protein"]["band"] == "medium"        # 8 / 32 = 0.25
        assert res["results"]["Interaction"]["band"] == "low"       # 4 / 30
        assert res["producer_id"] == p and res["signature"]["verified_at_release"] is True
        assert res["matched_public_topics"] == ["interactomics"]
    with c.app.state.sessionmaker() as db:
        assert db.query(Ticket).one().status == "CONSUMED"


def test_ticket_binds_request_scope_and_recipients(env):
    c, agents = env
    rid = approved_targeted(c, visibility="requester_only")
    c.post(f"/v1/requests/{rid}/run", headers=login(c, "persona_c"))
    (call,) = agents.calls
    t = call["ticket"]
    assert (t["request_id"], t["requester_id"], t["recipient_id"]) == (rid, "persona_c", "persona_d")
    assert t["result_recipients"] == ["persona_c"] and t["protocol"] == "psi_ca"
    assert t["exp"] - t["iat"] == 300
    assert c.get(f"/v1/requests/{rid}/result", headers=login(c, "persona_d")).status_code == 403


def test_only_requester_may_run_and_only_once(env):
    c, _ = env
    rid = approved_targeted(c)
    assert c.post(f"/v1/requests/{rid}/run", headers=login(c, "persona_d")).status_code == 403
    assert c.post(f"/v1/requests/{rid}/run", headers=login(c, "persona_a")).status_code == 404
    assert c.post(f"/v1/requests/{rid}/run", headers=login(c, "persona_c")).status_code == 202
    r = c.post(f"/v1/requests/{rid}/run", headers=login(c, "persona_c"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "request_completed"


@pytest.mark.parametrize("state", ["PENDING", "REJECTED"])
def test_unapproved_requests_cannot_run(env, state):
    c, agents = env
    r = c.post("/v1/researchers/persona_d/requests", headers=login(c, "persona_c"),
               json={"scope": scope(), "idempotency_key": uuid.uuid4().hex})
    rid = r.json()["id"]
    if state == "REJECTED":
        c.post(f"/v1/requests/{rid}/reject", headers=login(c, "persona_d"))
    assert c.post(f"/v1/requests/{rid}/run", headers=login(c, "persona_c")).status_code == 409
    assert agents.calls == []


def test_run_unavailable_without_keys(tmp_path):
    with make_client(tmp_path) as c:
        rid = approved_targeted(c)
        r = c.post(f"/v1/requests/{rid}/run", headers=login(c, "persona_c"))
        assert r.status_code == 503


# ---- package checks ----------------------------------------------------------------------------------

@pytest.mark.parametrize("mode,reason", [("extra_field", "package_rejected"), ("numeric", "package_rejected"),
                                         ("wrong_key", "package_signature_invalid"),
                                         ("error:local_topic_not_allowed", "local_topic_not_allowed")])
def test_bad_or_refused_packages_release_nothing(env, mode, reason):
    c, agents = env
    agents.mode = mode
    rid = approved_targeted(c)
    c.post(f"/v1/requests/{rid}/run", headers=login(c, "persona_c"))
    got = c.get(f"/v1/requests/{rid}", headers=login(c, "persona_c")).json()
    assert (got["status"], got["status_reason"]) == ("FAILED", reason)
    with c.app.state.sessionmaker() as db:
        assert db.query(ComparisonResult).count() == 0
        assert db.query(Ticket).one().status == "REVOKED"
    assert c.get(f"/v1/requests/{rid}/result", headers=login(c, "persona_c")).status_code == 409


# ---- revocation during computation ---------------------------------------------------------------------

def test_policy_tightening_during_compute_withholds_result(env):
    c, agents = env
    channel_id, rid = approved_channel_request(c)

    def owner_tightens(_request_id):
        from registry.app.models import Channel
        with c.app.state.sessionmaker() as db:
            ch = db.get(Channel, channel_id)
            ch.topics, ch.policy_version = ["proteomics"], ch.policy_version + 1
            revalidate_open_requests(db, c.app.state.clock, ch, "persona_a")
            db.commit()

    agents.during_compute = owner_tightens
    c.post(f"/v1/requests/{rid}/run", headers=login(c, "persona_b"))
    got = c.get(f"/v1/requests/{rid}", headers=login(c, "persona_b")).json()
    assert (got["status"], got["status_reason"]) == ("CANCELLED", "policy_incompatible")
    with c.app.state.sessionmaker() as db:
        assert db.query(ComparisonResult).count() == 0
        assert db.query(Ticket).one().status == "REVOKED"
        assert db.query(AuditEvent).filter_by(action="result.withhold").count() == 1


def test_pause_during_compute_keeps_approval_and_allows_rerun(env):
    c, agents = env
    channel_id, rid = approved_channel_request(c)

    def owner_pauses(_request_id):
        from registry.app.models import Channel
        with c.app.state.sessionmaker() as db:
            db.get(Channel, channel_id).status = "PAUSED"
            db.commit()

    agents.during_compute = owner_pauses
    c.post(f"/v1/requests/{rid}/run", headers=login(c, "persona_b"))
    got = c.get(f"/v1/requests/{rid}", headers=login(c, "persona_b")).json()
    assert (got["status"], got["status_reason"]) == ("APPROVED", "withheld_channel_paused")
    agents.during_compute = None
    c.post(f"/v1/channels/{channel_id}/resume", headers=login(c, "persona_a"))
    assert c.post(f"/v1/requests/{rid}/run", headers=login(c, "persona_b")).status_code == 202
    assert c.get(f"/v1/requests/{rid}", headers=login(c, "persona_b")).json()["status"] == "COMPLETED"
    with c.app.state.sessionmaker() as db:
        assert sorted(t.status for t in db.query(Ticket).all()) == ["CONSUMED", "REVOKED"]


def test_cancelling_request_revokes_outstanding_ticket(env):
    c, _ = env
    rid = approved_targeted(c)
    from registry.app.models import ComparisonRequest
    with c.app.state.sessionmaker() as db:  # simulate a ticket issued for a still-approved request
        from datetime import timedelta
        now = c.app.state.clock.now()
        db.add(Ticket(id="manual", request_id=rid, status="ISSUED", issued_at=now, expires_at=now + timedelta(minutes=5)))
        db.commit()
    c.post(f"/v1/requests/{rid}/cancel", headers=login(c, "persona_c"))
    with c.app.state.sessionmaker() as db:
        t = db.get(Ticket, "manual")
        assert (t.status, t.status_reason) == ("REVOKED", "requester_cancelled")
        assert db.get(ComparisonRequest, rid).status == "CANCELLED"


# ---- internal ticket-status endpoint ---------------------------------------------------------------------

def _status_call(c, keys_dir, issuer, ticket_id, replay_token=None):
    key = load_private(keys_dir / issuer / "private.pem")
    path = f"/internal/tickets/{ticket_id}"
    tok = replay_token or sign_service_token(key, issuer, "registry", "GET", path, b"",
                                             c.app.state.clock.now().timestamp())
    return c.get(path, headers={"X-Service-Token": tok}), tok


def test_ticket_status_requires_participant_agent(env, tmp_path):
    c, agents = env
    agents.mode = "error:hold"  # leave the ticket unconsumed
    rid = approved_targeted(c)
    with c.app.state.sessionmaker() as db:
        from datetime import timedelta
        now = c.app.state.clock.now()
        db.add(Ticket(id="tk1", request_id=rid, status="ISSUED", issued_at=now, expires_at=now + timedelta(minutes=5)))
        db.commit()
    keys_dir = tmp_path / "keys"
    r, tok = _status_call(c, keys_dir, "persona_c", "tk1")
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert _status_call(c, keys_dir, "persona_c", "tk1", replay_token=tok)[0].status_code == 401  # replay
    assert _status_call(c, keys_dir, "persona_a", "tk1")[0].status_code == 404                    # not a party
    assert _status_call(c, keys_dir, "registry", "tk1")[0].status_code == 401                     # not an agent
    assert c.get("/internal/tickets/tk1").status_code == 401                                      # no token
