"""Phase 3 gate: scoped requests, manual approval, owner-only decisions, policy tightening, quotas."""
from __future__ import annotations

import itertools

import pytest

from registry.app.models import ComparisonRequest
from tests.registry.conftest import make_client

DAY = 24 * 3600
_keys = itertools.count()


def scope(**over) -> dict:
    return {"topics": ["proteomics"], "entity_classes": ["Protein"], "metric": "jaccard",
            "protocol": "psi_ca", "disclosure": "score_only", **over}


def body(result_visibility="requester_only", key=None, **scope_over) -> dict:
    return {"scope": scope(**scope_over), "result_visibility": result_visibility,
            "idempotency_key": key or f"key-{next(_keys):06d}"}


def code(r) -> str:
    return r.json()["detail"]["code"]


@pytest.fixture
def channel(open_channel):
    return open_channel("persona_a", topics=["proteomics", "mass_spectrometry"])


@pytest.fixture
def ask(client, login):
    def _ask(requester: str, channel_id: str, **kw):
        return client.post(f"/v1/channels/{channel_id}/requests", json=body(**kw), headers=login(requester))
    return _ask


@pytest.fixture
def decide(client, login):
    def _decide(actor: str, request_id: str, action: str):
        return client.post(f"/v1/requests/{request_id}/{action}", headers=login(actor))
    return _decide


# ---- Journey A: one-to-many ------------------------------------------------------------------

def test_journey_a_three_requesters_three_outcomes(client, login, channel, ask, decide):
    ids = {}
    for p in ("persona_b", "persona_c", "persona_d"):
        r = ask(p, channel["id"], topics=["mass_spectrometry"] if p != "persona_d" else ["proteomics"])
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "PENDING" and r.json()["recipient"]["researcher_id"] == "persona_a"
        ids[p] = r.json()["id"]

    inbox = client.get("/v1/requests/inbox", headers=login("persona_a")).json()["requests"]
    assert sorted(i["id"] for i in inbox) == sorted(ids.values())
    assert all(i["requested_scope"]["protocol"] == "psi_ca" for i in inbox)

    approved = decide("persona_a", ids["persona_b"], "approve").json()
    assert approved["status"] == "APPROVED" and approved["approved_policy_version"] == 1
    assert approved["execution_check"] == {"ok": True, "reason": None}
    assert decide("persona_a", ids["persona_c"], "reject").json()["status"] == "REJECTED"

    status = {p: client.get(f"/v1/requests/{i}", headers=login(p)).json()["status"] for p, i in ids.items()}
    assert status == {"persona_b": "APPROVED", "persona_c": "REJECTED", "persona_d": "PENDING"}
    for p in ("persona_c", "persona_d"):
        r = client.get(f"/v1/requests/{ids[p]}/result", headers=login(p))
        assert r.status_code == 409 and code(r) == "result_unavailable"


def test_notifications_follow_the_workflow(client, login, channel, ask, decide):
    rid = ask("persona_b", channel["id"]).json()["id"]
    a_notes = client.get("/v1/notifications", headers=login("persona_a")).json()["notifications"]
    assert [(n["kind"], n["request_id"]) for n in a_notes] == [("request_received", rid)]
    decide("persona_a", rid, "approve")
    b_notes = client.get("/v1/notifications", headers=login("persona_b")).json()["notifications"]
    assert [n["kind"] for n in b_notes] == ["request_approved"]
    nid = b_notes[0]["id"]
    assert client.post(f"/v1/notifications/{nid}/read", headers=login("persona_c")).status_code == 404
    assert client.post(f"/v1/notifications/{nid}/read", headers=login("persona_b")).json()["read"] is True
    assert client.get("/v1/notifications?unread_only=true", headers=login("persona_b")).json()["notifications"] == []


# ---- Journey B: targeted one-to-one ------------------------------------------------------------

def test_journey_b_targeted_request(client, login, decide):
    r = client.post("/v1/researchers/persona_d/requests", headers=login("persona_c"),
                    json=body(topics=["interactomics"], result_visibility="both"))
    assert r.status_code == 201 and r.json()["kind"] == "targeted"
    rid = r.json()["id"]
    assert decide("persona_c", rid, "approve").status_code == 403  # requester cannot self-approve
    r = decide("persona_d", rid, "approve")
    assert r.json()["status"] == "APPROVED" and r.json()["approved_policy_version"] is None
    assert r.json()["execution_check"]["ok"] is True


def test_targeted_scope_limited_to_recipient_published_topics(client, login):
    r = client.post("/v1/researchers/persona_d/requests", headers=login("persona_c"),
                    json=body(topics=["antiviral_signaling"]))  # persona_d's *private* topic
    assert r.status_code == 422 and code(r) == "topic_outside_policy"


@pytest.mark.parametrize("target", ["persona_e", "persona_z"])
def test_cannot_target_unverified_or_unknown(client, login, target):
    r = client.post(f"/v1/researchers/{target}/requests", headers=login("persona_c"), json=body())
    assert r.status_code == 404


def test_cannot_request_self(client, login, channel):
    assert client.post("/v1/researchers/persona_a/requests", headers=login("persona_a"), json=body()).status_code == 422
    assert client.post(f"/v1/channels/{channel['id']}/requests", headers=login("persona_a"),
                       json=body()).status_code == 422


# ---- authorization ------------------------------------------------------------------------------

@pytest.mark.parametrize("actor", ["persona_b", "persona_c", "persona_d"])
def test_only_recipient_may_approve_or_reject(client, channel, ask, decide, actor):
    rid = ask("persona_b", channel["id"]).json()["id"]
    for action in ("approve", "reject"):
        r = decide(actor, rid, action)
        assert r.status_code in (403, 404), (actor, action)  # requester 403; third parties 404
        assert r.status_code == (403 if actor == "persona_b" else 404)


def test_only_requester_may_cancel(client, channel, ask, decide):
    rid = ask("persona_b", channel["id"]).json()["id"]
    assert decide("persona_a", rid, "cancel").status_code == 403
    assert decide("persona_b", rid, "cancel").json()["status"] == "CANCELLED"


def test_third_parties_cannot_see_requests(client, login, channel, ask):
    rid = ask("persona_b", channel["id"]).json()["id"]
    for p in ("persona_c", "persona_d"):
        assert client.get(f"/v1/requests/{rid}", headers=login(p)).status_code == 404
        assert rid not in [i["id"] for i in client.get("/v1/requests/inbox", headers=login(p)).json()["requests"]]


def test_unverified_cannot_request_or_decide(client, login, channel, ask):
    rid = ask("persona_b", channel["id"]).json()["id"]
    h = login("persona_e")
    assert client.post(f"/v1/channels/{channel['id']}/requests", json=body(), headers=h).status_code == 403
    assert client.post("/v1/researchers/persona_a/requests", json=body(), headers=h).status_code == 403
    assert client.post(f"/v1/requests/{rid}/approve", headers=h).status_code == 403
    assert client.get("/v1/requests/inbox", headers=h).status_code == 403


def test_requester_only_result_hidden_from_recipient(client, login, channel, ask, decide):
    rid = ask("persona_b", channel["id"], result_visibility="requester_only").json()["id"]
    decide("persona_a", rid, "approve")
    r = client.get(f"/v1/requests/{rid}/result", headers=login("persona_a"))
    assert r.status_code == 403 and code(r) == "result_not_visible"


@pytest.mark.parametrize("first,second", [("approve", "approve"), ("approve", "reject"), ("reject", "approve")])
def test_decisions_are_final(channel, ask, decide, first, second):
    rid = ask("persona_b", channel["id"]).json()["id"]
    assert decide("persona_a", rid, first).status_code == 200
    assert decide("persona_a", rid, second).status_code == 409


# ---- scope validation ---------------------------------------------------------------------------

@pytest.mark.parametrize("over,status,expected", [
    ({"disclosure": "evidence"}, 403, "evidence_disabled"),
    ({"disclosure": "summary"}, 422, "disclosure_exceeds_policy"),   # channel max is score_only
    ({"topics": ["quantitative_proteomics"]}, 422, "topic_outside_policy"),
    ({"protocol": "plaintext_dev"}, 422, "protocol_not_enabled"),
])
def test_scope_rejections(ask, channel, over, status, expected):
    r = ask("persona_b", channel["id"], **over)
    assert r.status_code == status and code(r) == expected


@pytest.mark.parametrize("over", [{"normalization": "other/2"}, {"entity_classes": ["Gene"]},
                                  {"metric": "cosine"}, {"protocol": "psi"}])
def test_scope_schema_is_closed(ask, channel, over):
    assert ask("persona_b", channel["id"], **over).status_code == 422


def test_result_visibility_must_be_allowed(client, login, open_channel, ask):
    h = login("persona_a")
    ch = client.post("/v1/channels", headers=h, json={"topics": ["proteomics"],
                                                      "allowed_result_visibility": ["requester_only"]}).json()
    client.post(f"/v1/channels/{ch['id']}/activate", headers=h)
    r = ask("persona_b", ch["id"], result_visibility="both")
    assert r.status_code == 422 and code(r) == "result_visibility_not_allowed"


def test_channel_cannot_offer_evidence(client, login):
    r = client.post("/v1/channels", headers=login("persona_a"),
                    json={"topics": ["proteomics"], "max_disclosure": "evidence"})
    assert r.status_code == 422


def test_plaintext_dev_accepted_only_with_flag(tmp_path):
    with make_client(tmp_path, dev_plaintext_matcher=True) as c:
        token = c.post("/v1/auth/demo-login", json={"researcher_id": "persona_c"}).json()["access_token"]
        r = c.post("/v1/researchers/persona_d/requests", headers={"Authorization": f"Bearer {token}"},
                   json=body(topics=["interactomics"], protocol="plaintext_dev"))
        assert r.status_code == 201 and r.json()["requested_scope"]["protocol"] == "plaintext_dev"


# ---- channel state gates --------------------------------------------------------------------------

def test_paused_closed_expired_channels_block_new_requests(client, login, channel, ask, advance):
    h = login("persona_a")
    client.post(f"/v1/channels/{channel['id']}/pause", headers=h)
    r = ask("persona_b", channel["id"])
    assert r.status_code == 409 and code(r) == "channel_not_accepting_requests"
    client.post(f"/v1/channels/{channel['id']}/resume", headers=h)
    assert ask("persona_b", channel["id"]).status_code == 201
    advance(DAY)
    r = ask("persona_c", channel["id"])
    assert r.status_code == 409 and code(r) == "channel_expired"


def test_draft_channel_requests_look_missing(client, open_channel, ask):
    draft = open_channel("persona_a", activate=False)
    assert ask("persona_b", draft["id"]).status_code == 404


def test_closing_channel_cancels_unfinished_requests(client, login, channel, ask, decide):
    pending = ask("persona_b", channel["id"]).json()["id"]
    approved = ask("persona_c", channel["id"]).json()["id"]
    decide("persona_a", approved, "approve")
    rejected = ask("persona_d", channel["id"]).json()["id"]
    decide("persona_a", rejected, "reject")
    client.post(f"/v1/channels/{channel['id']}/close", headers=login("persona_a"))
    got = {rid: client.get(f"/v1/requests/{rid}", headers=login("persona_a")).json()
           for rid in (pending, approved, rejected)}
    assert (got[pending]["status"], got[pending]["status_reason"]) == ("CANCELLED", "channel_closed")
    assert (got[approved]["status"], got[approved]["status_reason"]) == ("CANCELLED", "channel_closed")
    assert got[rejected]["status"] == "REJECTED"  # decided requests keep their outcome


def test_expiry_expires_pending_and_approved(client, login, channel, ask, decide, advance):
    pending = ask("persona_b", channel["id"]).json()["id"]
    approved = ask("persona_c", channel["id"]).json()["id"]
    decide("persona_a", approved, "approve")
    advance(DAY)
    h = login("persona_a")
    for rid in (pending, approved):
        assert client.get(f"/v1/requests/{rid}", headers=h).json()["status"] == "EXPIRED"
    assert decide("persona_a", pending, "approve").status_code == 409
    assert decide("persona_c", approved, "cancel").status_code == 409


def test_targeted_request_lapses_after_ttl(client, login, decide, advance):
    rid = client.post("/v1/researchers/persona_d/requests", headers=login("persona_c"),
                      json=body(topics=["interactomics"])).json()["id"]
    advance(72 * 3600)
    r = decide("persona_d", rid, "approve")
    assert r.status_code == 409 and code(r) == "request_expired"


def test_paused_channel_blocks_execution_of_approved_request(client, login, channel, ask, decide):
    rid = ask("persona_b", channel["id"]).json()["id"]
    decide("persona_a", rid, "approve")
    client.post(f"/v1/channels/{channel['id']}/pause", headers=login("persona_a"))
    check = client.get(f"/v1/requests/{rid}", headers=login("persona_b")).json()["execution_check"]
    assert check == {"ok": False, "reason": "channel_paused"}


# ---- policy tightening ---------------------------------------------------------------------------

def test_tightening_invalidates_incompatible_requests_only(client, login, channel, ask, decide):
    ms_pending = ask("persona_b", channel["id"], topics=["mass_spectrometry"]).json()["id"]
    ms_approved = ask("persona_c", channel["id"], topics=["mass_spectrometry"]).json()["id"]
    decide("persona_a", ms_approved, "approve")
    prot_approved = ask("persona_d", channel["id"], topics=["proteomics"]).json()["id"]
    decide("persona_a", prot_approved, "approve")

    r = client.patch(f"/v1/channels/{channel['id']}", headers=login("persona_a"),
                     json={"topics": ["proteomics"], "expected_policy_version": 1})
    assert r.status_code == 200 and r.json()["policy_version"] == 2
    h = login("persona_a")
    got = {rid: client.get(f"/v1/requests/{rid}", headers=h).json() for rid in (ms_pending, ms_approved, prot_approved)}
    assert (got[ms_pending]["status"], got[ms_pending]["status_reason"]) == ("CANCELLED", "policy_incompatible")
    assert (got[ms_approved]["status"], got[ms_approved]["status_reason"]) == ("CANCELLED", "policy_incompatible")
    assert got[prot_approved]["status"] == "APPROVED"
    assert got[prot_approved]["execution_check"]["ok"] is True

    # New requests are checked against version 2.
    r = ask("persona_b", channel["id"], topics=["mass_spectrometry"])
    assert r.status_code == 422 and code(r) == "topic_outside_policy"
    kinds = [n["kind"] for n in client.get("/v1/notifications", headers=login("persona_c")).json()["notifications"]]
    assert "request_invalidated" in kinds


def test_restricting_result_visibility_invalidates_both_visibility_requests(client, login, channel, ask, decide):
    both = ask("persona_b", channel["id"], result_visibility="both").json()["id"]
    decide("persona_a", both, "approve")
    client.patch(f"/v1/channels/{channel['id']}", headers=login("persona_a"),
                 json={"allowed_result_visibility": ["requester_only"], "expected_policy_version": 1})
    assert client.get(f"/v1/requests/{both}", headers=login("persona_b")).json()["status"] == "CANCELLED"


def test_policy_versions_endpoint_is_owner_only(client, login, channel):
    client.patch(f"/v1/channels/{channel['id']}", headers=login("persona_a"),
                 json={"max_disclosure": "summary", "expected_policy_version": 1})
    versions = client.get(f"/v1/channels/{channel['id']}/policy-versions", headers=login("persona_a")).json()
    assert [(v["version"], v["max_disclosure"]) for v in versions["versions"]] == [(1, "score_only"), (2, "summary")]
    assert client.get(f"/v1/channels/{channel['id']}/policy-versions", headers=login("persona_b")).status_code == 404


# ---- idempotency, duplicates, quotas ---------------------------------------------------------------

def test_idempotent_replay_returns_same_request(client, login, channel):
    h = login("persona_b")
    payload = body(key="replay-key-1")
    first = client.post(f"/v1/channels/{channel['id']}/requests", json=payload, headers=h)
    again = client.post(f"/v1/channels/{channel['id']}/requests", json=payload, headers=h)
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["id"] == again.json()["id"]
    with client.app.state.sessionmaker() as db:
        assert db.query(ComparisonRequest).count() == 1


def test_idempotency_key_reuse_with_different_payload_conflicts(client, login, channel):
    h = login("persona_b")
    client.post(f"/v1/channels/{channel['id']}/requests", json=body(key="replay-key-2"), headers=h)
    r = client.post(f"/v1/channels/{channel['id']}/requests", headers=h,
                    json=body(key="replay-key-2", topics=["mass_spectrometry"]))
    assert r.status_code == 409 and code(r) == "idempotency_conflict"


def test_duplicate_open_request_refused(ask, channel, decide):
    first = ask("persona_b", channel["id"]).json()["id"]
    r = ask("persona_b", channel["id"])
    assert r.status_code == 409 and code(r) == "duplicate_open_request"
    assert r.json()["detail"]["existing_request_id"] == first
    decide("persona_b", first, "cancel")
    assert ask("persona_b", channel["id"]).status_code == 201  # allowed once the first is closed


def test_distinct_scope_quota_per_pair(ask, channel):
    variants = [dict(topics=["proteomics"]), dict(topics=["mass_spectrometry"]),
                dict(topics=["proteomics", "mass_spectrometry"]), dict(topics=["proteomics"], metric="overlap_count")]
    codes = [ask("persona_b", channel["id"], **v).status_code for v in variants]
    assert codes == [201, 201, 201, 429]
    # Other requesters have their own quota.
    assert ask("persona_c", channel["id"], **variants[3]).status_code == 201


def test_pair_rate_limit_counts_cancelled_attempts(ask, channel, decide):
    statuses = []
    for _ in range(6):
        r = ask("persona_b", channel["id"])
        statuses.append(r.status_code)
        if r.status_code == 201:
            decide("persona_b", r.json()["id"], "cancel")
    assert statuses == [201] * 5 + [429]


def test_quota_is_a_rolling_24h_window(client, login, decide, advance):
    # Targeted requests live 72h, so the window can roll over while the target is still reachable.
    def targeted():
        return client.post("/v1/researchers/persona_d/requests", headers=login("persona_c"),
                           json=body(topics=["interactomics"]))
    for _ in range(5):
        decide("persona_c", targeted().json()["id"], "cancel")
    assert targeted().status_code == 429
    advance(DAY - 60)
    assert targeted().status_code == 429
    advance(61)
    assert targeted().status_code == 201


# ---- audit -------------------------------------------------------------------------------------------

def test_audit_is_scoped_and_records_denials(client, login, channel, ask, decide):
    rid = ask("persona_b", channel["id"]).json()["id"]
    decide("persona_c", rid, "approve")            # third party: 404, no event on the request
    decide("persona_b", rid, "approve")            # requester: denied and audited
    decide("persona_a", rid, "approve")
    ask("persona_b", channel["id"], disclosure="evidence")

    a_events = client.get("/v1/audit", headers=login("persona_a")).json()["events"]
    assert {"channel.create", "channel.activate", "request.create", "request.approve"} <= {e["action"] for e in a_events}
    assert any(e["action"] == "request.approve" and e["decision"] == "deny" and e["actor_id"] == "persona_b"
               for e in a_events)
    b_events = client.get("/v1/audit", headers=login("persona_b")).json()["events"]
    assert any(e["reason_code"] == "evidence_disabled" for e in b_events)
    d_events = client.get("/v1/audit", headers=login("persona_d")).json()["events"]
    assert all(e["actor_id"] == "persona_d" for e in d_events)
