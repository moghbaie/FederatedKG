"""Phase 3 races against real Postgres row locks (nginx -> registry -> Postgres).

Tokens are obtained before the parallel section and a barrier releases all workers at once, so
the requests genuinely overlap inside the registry.
"""
from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from tests.integration.test_registry_live import api, login  # noqa: F401  (fixture + helper)

pytestmark = pytest.mark.live


def scope(topics):
    return {"topics": topics, "entity_classes": ["Protein"], "metric": "jaccard", "protocol": "psi_ca",
            "disclosure": "score_only"}


def new_channel(api: httpx.Client, topics=("proteomics", "mass_spectrometry")) -> str:
    a = login(api, "persona_a")
    ch = api.post("/v1/channels", json={"topics": list(topics)}, headers=a).json()
    api.post(f"/v1/channels/{ch['id']}/activate", headers=a)
    return ch["id"]


def together(*calls: Callable[[], httpx.Response]) -> list[httpx.Response]:
    """Run calls in parallel, each on its own connection, released simultaneously."""
    barrier = threading.Barrier(len(calls))

    def run(call):
        barrier.wait()
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(run, calls))


def client_for(api: httpx.Client) -> httpx.Client:
    return httpx.Client(base_url=api.base_url, timeout=20)


def submit_call(api, headers, channel_id, topics, key=None):
    def call():
        with client_for(api) as c:
            return c.post(f"/v1/channels/{channel_id}/requests", headers=headers,
                          json={"scope": scope(topics), "idempotency_key": key or uuid.uuid4().hex})
    return call


def test_approval_racing_policy_tightening_never_leaves_incompatible_approval(api):
    for _ in range(10):
        api.post("/v1/test/reset")
        cid = new_channel(api)
        b, a = login(api, "persona_b"), login(api, "persona_a")
        rid = submit_call(api, b, cid, ["mass_spectrometry"])().json()["id"]

        def approve():
            with client_for(api) as c:
                return c.post(f"/v1/requests/{rid}/approve", headers=a)

        def tighten():
            with client_for(api) as c:
                return c.patch(f"/v1/channels/{cid}", headers=a,
                               json={"topics": ["proteomics"], "expected_policy_version": 1})

        approved, tightened = together(approve, tighten)
        assert tightened.status_code == 200 and approved.status_code in (200, 409)
        final = api.get(f"/v1/requests/{rid}", headers=a).json()
        assert (final["status"], final["status_reason"]) == ("CANCELLED", "policy_incompatible"), final


def test_parallel_duplicate_submissions_create_one_request(api):
    cid = new_channel(api)
    b = login(api, "persona_b")
    codes = [r.status_code for r in together(*[submit_call(api, b, cid, ["proteomics"]) for _ in range(8)])]
    assert sorted(codes) == [201] + [409] * 7, codes


def test_parallel_replays_of_one_idempotency_key(api):
    cid = new_channel(api)
    b, key = login(api, "persona_b"), uuid.uuid4().hex
    rs = together(*[submit_call(api, b, cid, ["proteomics"], key=key) for _ in range(8)])
    assert sorted(r.status_code for r in rs) == [200] * 7 + [201], [r.status_code for r in rs]
    assert len({r.json()["id"] for r in rs}) == 1


def targeted_call(api, headers, key=None):
    def call():
        with client_for(api) as c:
            return c.post("/v1/researchers/persona_d/requests", headers=headers,
                          json={"scope": scope(["interactomics"]), "idempotency_key": key or uuid.uuid4().hex})
    return call


def test_parallel_targeted_duplicates_create_one_request(api):
    # No channel row serializes targeted requests; the per-requester lock must.
    c = login(api, "persona_c")
    codes = [r.status_code for r in together(*[targeted_call(api, c) for _ in range(8)])]
    assert sorted(codes) == [201] + [409] * 7, codes


def test_parallel_targeted_replays_of_one_key(api):
    c, key = login(api, "persona_c"), uuid.uuid4().hex
    rs = together(*[targeted_call(api, c, key=key) for _ in range(8)])
    assert sorted(r.status_code for r in rs) == [200] * 7 + [201], [r.status_code for r in rs]


def test_request_racing_channel_close_never_survives_open(api):
    for _ in range(10):
        api.post("/v1/test/reset")
        cid = new_channel(api)
        a, c_hdr = login(api, "persona_a"), login(api, "persona_c")

        def close():
            with client_for(api) as c:
                return c.post(f"/v1/channels/{cid}/close", headers=a)

        req, closed = together(submit_call(api, c_hdr, cid, ["proteomics"]), close)
        assert closed.status_code == 200
        if req.status_code == 201:
            final = api.get(f"/v1/requests/{req.json()['id']}", headers=a).json()
            assert final["status"] == "CANCELLED", final
        else:
            assert req.status_code == 409
