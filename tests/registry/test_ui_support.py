"""Registry features added for the web UI: EdDSA user tokens, registry clock header, contact requests."""
from __future__ import annotations

from datetime import datetime

import jwt

from fkg_protocol.keys import Keyring
from fkg_protocol.users import verify_user_token
from registry.app.models import Notification
from tests.registry.test_execution import approved_targeted, env, login  # noqa: F401  (fixture + helpers)


def test_user_tokens_are_eddsa_and_agent_verifiable(env, tmp_path):
    c, _ = env
    tok = c.post("/v1/auth/demo-login", json={"researcher_id": "persona_a"}).json()["access_token"]
    assert jwt.get_unverified_header(tok)["alg"] == "EdDSA"
    registry_key = Keyring.from_dir(tmp_path / "keys" / "public").get("registry")
    claims = verify_user_token(tok, registry_key, c.app.state.clock.now().timestamp())
    assert claims["sub"] == "persona_a" and claims["aud"] == "fkg-web"


def test_hs256_tokens_rejected_once_keys_exist(env):
    c, _ = env
    forged = jwt.encode({"sub": "persona_a", "iss": "fkg-registry", "aud": "fkg-web", "iat": 0, "exp": 2**40,
                         "jti": "x"}, c.app.state.settings.token_secret, algorithm="HS256")
    assert c.get("/v1/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_registry_now_header_follows_test_clock(env):
    c, _ = env
    before = datetime.fromisoformat(c.get("/v1/health").headers["X-Registry-Now"])
    c.post("/v1/test/clock/advance", json={"seconds": 3600})
    after = datetime.fromisoformat(c.get("/v1/health").headers["X-Registry-Now"])
    assert (after - before).total_seconds() >= 3600


def test_contact_request_is_manual_once_and_party_only(env):
    c, _ = env
    rid = approved_targeted(c)
    r = c.post(f"/v1/requests/{rid}/contact", headers=login(c, "persona_c"))
    assert r.status_code == 409  # not completed yet: no contact from a topic match or approval alone
    c.post(f"/v1/requests/{rid}/run", headers=login(c, "persona_c"))
    for _ in range(2):
        r = c.post(f"/v1/requests/{rid}/contact", headers=login(c, "persona_c"))
        assert r.status_code == 200 and r.json()["delivered"] == "in-app notification only"
    assert c.post(f"/v1/requests/{rid}/contact", headers=login(c, "persona_a")).status_code == 404
    with c.app.state.sessionmaker() as db:
        notes = db.query(Notification).filter_by(request_id=rid, kind="contact_requested").all()
    assert [n.recipient_id for n in notes] == ["persona_d"]
