from __future__ import annotations

import jwt
import pytest

from registry.app.models import AuditEvent
from tests.registry.conftest import PERSONAS, VERIFIED, make_client


@pytest.mark.parametrize("persona", PERSONAS)
def test_demo_login_and_me(client, login, persona):
    me = client.get("/v1/me", headers=login(persona)).json()
    assert me["researcher_id"] == persona
    assert me["is_simulated"] is True
    assert me["verified_researcher"] is (persona != "persona_e")


def test_login_is_labelled_demo_and_rejects_unknown(client):
    assert client.post("/v1/auth/demo-login", json={"researcher_id": "persona_a"}).json()["demo_login"] is True
    assert client.post("/v1/auth/demo-login", json={"researcher_id": "matthias_mann"}).status_code == 401


@pytest.mark.parametrize("header", [None, "Bearer not-a-token", "Basic abc"])
def test_missing_or_garbage_token_is_401(client, header):
    headers = {"Authorization": header} if header else {}
    assert client.get("/v1/me", headers=headers).status_code == 401


def test_forged_tokens_are_rejected(client):
    claims = {"sub": "persona_a", "iss": "fkg-registry", "aud": "fkg-web", "iat": 0, "exp": 2**40, "jti": "x"}
    wrong_key = jwt.encode(claims, "attacker-key", algorithm="HS256")
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {wrong_key}"}).status_code == 401
    secret = client.app.state.settings.token_secret
    wrong_aud = jwt.encode({**claims, "aud": "other"}, secret, algorithm="HS256")
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {wrong_aud}"}).status_code == 401
    unsigned = jwt.encode(claims, None, algorithm="none")
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {unsigned}"}).status_code == 401


def test_token_expires_on_registry_clock(client, login, advance):
    h = login("persona_a")
    advance(29 * 60)
    assert client.get("/v1/me", headers=h).status_code == 200
    advance(61)
    r = client.get("/v1/me", headers=h)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "token_expired"


def test_unverified_account_is_denied_and_audited(client, login):
    h = login("persona_e")
    for method, path, body in [("GET", "/v1/researchers", None), ("GET", "/v1/channels", None),
                               ("GET", "/v1/channels/mine", None),
                               ("POST", "/v1/channels", {"topics": ["proteomics"]})]:
        r = client.request(method, path, headers=h, json=body)
        assert r.status_code == 403, (path, r.text)
        assert r.json()["detail"]["code"] == "unverified_researcher"
    with client.app.state.sessionmaker() as db:
        denials = db.query(AuditEvent).filter_by(actor_id="persona_e", decision="deny").count()
    assert denials == 4


def test_directory_lists_other_verified_researchers_ranked(client, login, ground_truth):
    entries = client.get("/v1/researchers", headers=login("persona_a")).json()["researchers"]
    ids = [e["researcher_id"] for e in entries]
    assert sorted(ids) == ["persona_b", "persona_c", "persona_d"]
    for e in entries:
        gt = ground_truth["topic_similarity"][f"persona_a|{e['researcher_id']}"]
        assert e["topic_match"]["score"] == gt["jaccard"]
        assert e["topic_match"]["matched_topics"] == gt["matched_topics"]
    scores = [e["topic_match"]["score"] for e in entries]
    assert scores == sorted(scores, reverse=True)


def test_directory_exposes_public_profile_fields_only(client, login):
    allowed = {"researcher_id", "display_name", "theme", "verified_researcher", "published_topics",
               "is_simulated", "public_scientific_inspiration", "topic_match"}
    for e in client.get("/v1/researchers", headers=login("persona_b")).json()["researchers"]:
        assert set(e) == allowed


def test_test_endpoints_absent_outside_test_mode(tmp_path):
    with make_client(tmp_path, test_mode=False) as c:
        assert c.get("/v1/test/clock").status_code == 404
        assert c.post("/v1/test/clock/advance", json={"seconds": 60}).status_code == 404
        assert c.post("/v1/test/reset").status_code == 404
        assert c.get("/v1/health").json()["test_mode"] is False


def test_clock_cannot_move_backwards(client):
    assert client.post("/v1/test/clock/advance", json={"seconds": -5}).status_code == 422


def test_audit_never_stores_tokens(client, login):
    for p in VERIFIED:
        login(p)
    with client.app.state.sessionmaker() as db:
        rows = db.query(AuditEvent).all()
    assert rows and not any("eyJ" in str(v) for r in rows for v in vars(r).values())
