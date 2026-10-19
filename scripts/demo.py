"""Narrated, reproducible demo of the FederatedKG workflow through the public API.

Runs Journey A (one-to-many channel), the pause / tighten / expiry controls, and Journey B
(targeted one-to-one), printing what happens and what each party can see. Requires the stack
in test mode. It resets the demo first, so every run produces the same outcome.

Usage: uv run python scripts/demo.py [base_url]       (default http://localhost:8080)
"""
from __future__ import annotations

import sys
import time
import uuid

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080").rstrip("/") + "/api"
api = httpx.Client(base_url=BASE, timeout=60)
NAMES = {"persona_a": "A", "persona_b": "B", "persona_c": "C", "persona_d": "D", "persona_e": "E"}


def say(text: str) -> None:
    print(f"\n>> {text}")


def show(text: str) -> None:
    print(f"    {text}")


def h(persona: str) -> dict:
    tok = api.post("/v1/auth/demo-login", json={"researcher_id": persona}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def scope(topics, classes=("Protein",), disclosure="score_only"):
    return {"topics": list(topics), "entity_classes": list(classes), "metric": "jaccard", "protocol": "psi_ca",
            "disclosure": disclosure}


def request(path: str, persona: str, topics, visibility="requester_only", **kw) -> dict:
    r = api.post(path, headers=h(persona), json={"scope": scope(topics, **kw), "result_visibility": visibility,
                                                 "idempotency_key": uuid.uuid4().hex})
    r.raise_for_status()
    return r.json()


def wait(rid: str, persona: str) -> dict:
    for _ in range(100):
        got = api.get(f"/v1/requests/{rid}", headers=h(persona)).json()
        if got["status"] != "RUNNING":
            return got
        time.sleep(0.3)
    raise SystemExit("comparison did not finish")


def result_line(rid: str, persona: str) -> str:
    r = api.get(f"/v1/requests/{rid}/result", headers=h(persona))
    if r.status_code != 200:
        return f"no result ({r.json()['detail']['code']})"
    body = r.json()
    bands = ", ".join(f"{cls}: {v['band']}" for cls, v in body["results"].items())
    return f"{bands}   [{body['method']}, signed by {body['producer_id']}]"


def main() -> None:
    health = api.get("/v1/health").json()
    if not health.get("test_mode"):
        raise SystemExit("The demo needs FKG_TEST_MODE=1 (default for the local stack).")
    api.post("/v1/test/reset")
    print("FederatedKG demo - simulated researchers and synthetic knowledge graphs. No real researcher participation.")

    say("Journey A: Persona A opens a 24-hour, topics-only channel for verified researchers")
    a = h("persona_a")
    ch = api.post("/v1/channels", headers=a, json={"topics": ["proteomics", "mass_spectrometry"]}).json()
    ch = api.post(f"/v1/channels/{ch['id']}/activate", headers=a).json()
    show(f"channel {ch['id'][:8]}  topics={ch['topics']}  expires_at={ch['expires_at']}")

    say("B, C and D discover it; each sees only the published topics and a topic-match score")
    for p in ("persona_b", "persona_c", "persona_d"):
        item = api.get("/v1/channels", headers=h(p)).json()["channels"][0]
        show(f"{NAMES[p]} sees topics {item['topics']} with topic similarity {item['topic_match']['score']}")
    show(f"E (unverified) gets HTTP {api.get('/v1/channels', headers=h('persona_e')).status_code}")

    say("B, C and D each request a PSI-CA comparison")
    reqs = {p: request(f"/v1/channels/{ch['id']}/requests", p, [t])["id"]
            for p, t in (("persona_b", "mass_spectrometry"), ("persona_c", "mass_spectrometry"), ("persona_d", "proteomics"))}

    say("A approves B, rejects C, and leaves D pending")
    api.post(f"/v1/requests/{reqs['persona_b']}/approve", headers=a)
    api.post(f"/v1/requests/{reqs['persona_c']}/reject", headers=a)

    say("B runs the approved comparison: the two agents run PSI-CA directly; no entity list is exchanged")
    api.post(f"/v1/requests/{reqs['persona_b']}/run", headers=h("persona_b"))
    show(f"B's request: {wait(reqs['persona_b'], 'persona_b')['status']}")
    show(f"B sees:  {result_line(reqs['persona_b'], 'persona_b')}")
    show(f"A sees:  {result_line(reqs['persona_b'], 'persona_a')}  (B asked for 'only me')")
    for p in ("persona_c", "persona_d"):
        st = api.get(f"/v1/requests/{reqs[p]}", headers=h(p)).json()["status"]
        show(f"{NAMES[p]}'s request is {st}; {NAMES[p]} sees: {result_line(reqs[p], p)}")

    say("A pauses the channel, then tightens the policy to 'proteomics' only")
    second = request(f"/v1/channels/{ch['id']}/requests", "persona_b", ["mass_spectrometry"], classes=("Interaction",))["id"]
    api.post(f"/v1/requests/{second}/approve", headers=a)
    api.post(f"/v1/channels/{ch['id']}/pause", headers=a)
    check = api.get(f"/v1/requests/{second}", headers=h("persona_b")).json()["execution_check"]
    show(f"B's second, approved request while paused: can run? {check['ok']} ({check['reason']})")
    api.patch(f"/v1/channels/{ch['id']}", headers=a, json={"topics": ["proteomics"], "expected_policy_version": 1})
    got = api.get(f"/v1/requests/{second}", headers=h("persona_b")).json()
    show(f"after tightening: {got['status']} ({got['status_reason']}); B's first result is unchanged")
    show(f"D's pending proteomics request still fits: {api.get(f'/v1/requests/{reqs['persona_d']}', headers=h('persona_d')).json()['status']}")

    say("A resumes and approves D; then 24 hours pass (demo clock)")
    api.post(f"/v1/channels/{ch['id']}/resume", headers=a)
    api.post(f"/v1/requests/{reqs['persona_d']}/approve", headers=a)
    api.post("/v1/test/clock/advance", json={"seconds": 24 * 3600})
    a = h("persona_a")
    show(f"channel: {api.get(f'/v1/channels/{ch['id']}', headers=a).json()['status']}")
    show(f"D's approved-but-unrun request: {api.get(f'/v1/requests/{reqs['persona_d']}', headers=h('persona_d')).json()['status']}")
    show(f"B can still see the earlier result: {result_line(reqs['persona_b'], 'persona_b')}")

    say("Journey B: C sends D a targeted one-to-one request (summary, result to both)")
    rid = request("/v1/researchers/persona_d/requests", "persona_c", ["interactomics"], visibility="both",
                  classes=("Protein", "Interaction"), disclosure="summary")["id"]
    api.post(f"/v1/requests/{rid}/approve", headers=h("persona_d"))
    api.post(f"/v1/requests/{rid}/run", headers=h("persona_c"))
    show(f"status: {wait(rid, 'persona_c')['status']}")
    show(f"C sees:  {result_line(rid, 'persona_c')}")
    show(f"D sees:  {result_line(rid, 'persona_d')}")
    show(f"A (not a party) gets HTTP {api.get(f'/v1/requests/{rid}', headers=h('persona_a')).status_code}")

    say("Audit: A's trail records every decision, policy version, release and expiry")
    events = api.get("/v1/audit", headers=h("persona_a")).json()["events"]
    show(", ".join(sorted({e["action"] for e in events})))
    print("\nDone. Open http://localhost:8080 to explore the same state in the web app.")


if __name__ == "__main__":
    main()
