"""Phase 2 against the real stack (nginx -> registry -> Postgres): migrations, expiry, row locks."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

pytestmark = pytest.mark.live


@pytest.fixture
def api(live_stack):
    with httpx.Client(base_url=f"{live_stack}/api", timeout=10) as c:
        assert c.post("/v1/test/reset").status_code == 200, "stack must run with FKG_TEST_MODE=1"
        yield c
        c.post("/v1/test/reset")


def login(api: httpx.Client, persona: str) -> dict:
    token = api.post("/v1/auth/demo-login", json={"researcher_id": persona}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_journey_a_discovery_and_expiry(api):
    a = login(api, "persona_a")
    ch = api.post("/v1/channels", json={"topics": ["proteomics", "mass_spectrometry"]}, headers=a).json()
    ch = api.post(f"/v1/channels/{ch['id']}/activate", headers=a).json()
    for viewer in ("persona_b", "persona_c", "persona_d"):
        ids = [c["id"] for c in api.get("/v1/channels", headers=login(api, viewer)).json()["channels"]]
        assert ch["id"] in ids, viewer
    assert api.get("/v1/channels", headers=login(api, "persona_e")).status_code == 403

    api.post("/v1/test/clock/advance", json={"seconds": 24 * 3600})
    assert api.get("/v1/channels", headers=login(api, "persona_b")).json()["channels"] == []
    a = login(api, "persona_a")
    assert api.get("/v1/channels/mine", headers=a).json()["channels"][0]["status"] == "EXPIRED"
    assert api.post(f"/v1/channels/{ch['id']}/close", headers=a).status_code == 409


def test_concurrent_policy_edits_admit_exactly_one(api):
    a = login(api, "persona_a")
    ch = api.post("/v1/channels", json={"topics": ["proteomics", "mass_spectrometry"]}, headers=a).json()
    api.post(f"/v1/channels/{ch['id']}/activate", headers=a)

    def edit(i: int) -> int:
        topics = ["proteomics"] if i % 2 else ["mass_spectrometry"]
        return api.patch(f"/v1/channels/{ch['id']}", headers=a,
                         json={"topics": topics, "expected_policy_version": 1}).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(edit, range(8)))
    assert sorted(codes) == [200] + [409] * 7, codes
    assert api.get(f"/v1/channels/{ch['id']}", headers=a).json()["policy_version"] == 2


def test_tokens_from_the_api_never_appear_in_audit_or_logs(api, live_stack):
    from tests.conftest import compose
    login(api, "persona_a")
    logs = compose("logs", "--no-color", "registry", "frontend").stdout
    assert "eyJ" not in logs
