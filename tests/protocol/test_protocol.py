"""Service tokens, tickets and result packages: signing, binding, replay and disclosure rules."""
from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from fkg_protocol.keys import Keyring, generate, load_private
from fkg_protocol.results import band, package_violations, shape, sign_package, size_bucket, verify_package
from fkg_protocol.tickets import counterpart, issue_ticket, verify_ticket
from fkg_protocol.tokens import AuthError, ReplayCache, sign_service_token, verify_service_token

NOW = time.time()


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    root = tmp_path_factory.mktemp("keys")
    services = ["registry", "persona_a", "persona_b"]
    generate({s: root / s for s in services}, root / "public")
    return {s: load_private(root / s / "private.pem") for s in services}, Keyring.from_dir(root / "public")


def token(keys, issuer="persona_a", aud="persona_b", method="POST", path="/internal/psi/setup", body=b"{}", now=NOW):
    return sign_service_token(keys[0][issuer], issuer, aud, method, path, body, now)


def verify(keys, tok, aud="persona_b", method="POST", path="/internal/psi/setup", body=b"{}", now=NOW,
           replay=None, issuers=None):
    return verify_service_token(tok, keys[1], aud, method, path, body, replay or ReplayCache(), now, issuers)


# ---- keys ----------------------------------------------------------------------------------------

def test_generate_keeps_existing_keys(tmp_path):
    generate({"registry": tmp_path / "r"}, tmp_path / "pub")
    first = (tmp_path / "r" / "private.pem").read_bytes()
    assert generate({"registry": tmp_path / "r"}, tmp_path / "pub") == []
    assert (tmp_path / "r" / "private.pem").read_bytes() == first


# ---- service tokens ----------------------------------------------------------------------------

def test_valid_token_verifies(keys):
    assert verify(keys, token(keys))["iss"] == "persona_a"


@pytest.mark.parametrize("change,code", [
    ({"aud": "persona_a"}, "invalid_service_token"),
    ({"method": "GET"}, "token_request_mismatch"),
    ({"path": "/internal/psi/process"}, "token_request_mismatch"),
    ({"body": b'{"tampered":1}'}, "body_hash_mismatch"),
    ({"now": NOW + 120}, "service_token_expired"),
    ({"issuers": ("registry",)}, "issuer_not_allowed"),
])
def test_token_binding(keys, change, code):
    with pytest.raises(AuthError) as e:
        verify(keys, token(keys), **change)
    assert e.value.code == code


def test_replayed_token_rejected(keys):
    replay, tok = ReplayCache(), token(keys)
    verify(keys, tok, replay=replay)
    with pytest.raises(AuthError) as e:
        verify(keys, tok, replay=replay)
    assert e.value.code == "replayed_service_token"


def test_token_from_unknown_key_rejected(keys):
    rogue = Ed25519PrivateKey.generate()
    tok = sign_service_token(rogue, "persona_a", "persona_b", "POST", "/internal/psi/setup", b"{}", NOW)
    with pytest.raises(AuthError) as e:
        verify(keys, tok)
    assert e.value.code == "invalid_service_token"


def test_unsigned_or_hs256_tokens_rejected(keys):
    claims = jwt.decode(token(keys), options={"verify_signature": False})
    for forged in (jwt.encode(claims, None, algorithm="none", headers={"typ": "fkg-service"}),
                   jwt.encode(claims, "secret", algorithm="HS256", headers={"typ": "fkg-service"})):
        with pytest.raises(AuthError):
            verify(keys, forged)


def test_missing_token(keys):
    with pytest.raises(AuthError) as e:
        verify(keys, None)
    assert e.value.code == "missing_service_token"


# ---- tickets -------------------------------------------------------------------------------------

def claims(**over):
    return {"jti": "t1", "request_id": "r1", "requester_id": "persona_a", "recipient_id": "persona_b",
            "protocol": "psi_ca", "scope": {"topics": ["proteomics"]}, "scope_fingerprint": "f",
            "channel_id": None, "policy_version": None, "result_recipients": ["persona_a"], **over}


def test_ticket_roundtrip_with_nullable_fields(keys):
    t = verify_ticket(issue_ticket(keys[0]["registry"], claims(), NOW), keys[1].get("registry"), NOW)
    assert t["channel_id"] is None and t["result_recipients"] == ["persona_a"]


def test_ticket_signed_by_agent_rejected(keys):
    forged = issue_ticket(keys[0]["persona_a"], claims(), NOW)
    with pytest.raises(AuthError):
        verify_ticket(forged, keys[1].get("registry"), NOW)


def test_ticket_expires(keys):
    t = issue_ticket(keys[0]["registry"], claims(), NOW)
    with pytest.raises(AuthError) as e:
        verify_ticket(t, keys[1].get("registry"), NOW + 301)
    assert e.value.code == "ticket_expired"


def test_ticket_recipients_must_be_participants(keys):
    t = issue_ticket(keys[0]["registry"], claims(result_recipients=["persona_c"]), NOW)
    with pytest.raises(AuthError):
        verify_ticket(t, keys[1].get("registry"), NOW)


def test_service_token_is_not_a_ticket(keys):
    with pytest.raises(AuthError):
        verify_ticket(token(keys, issuer="registry"), keys[1].get("registry"), NOW)


def test_counterpart():
    assert counterpart(claims(), "persona_a") == "persona_b"
    with pytest.raises(AuthError):
        counterpart(claims(), "persona_c")


# ---- results -------------------------------------------------------------------------------------

@pytest.mark.parametrize("inter,union,expected", [(0, 40, "insufficient_disclosure"), (2, 3, "insufficient_disclosure"),
                                                  (4, 36, "low"), (8, 32, "medium"), (12, 26, "high")])
def test_jaccard_bands(inter, union, expected):
    assert band("jaccard", inter, union) == expected


def test_count_bands():
    assert [band("overlap_count", n, 0) for n in (2, 3, 6, 10)] == ["insufficient_disclosure", "low", "medium", "high"]


def test_shape_respects_disclosure():
    assert set(shape("score_only", "jaccard", 8, 19, 21)) == {"band"}
    summary = shape("summary", "jaccard", 8, 19, 21)
    assert summary["set_size_buckets"] == {"own": "10-24", "counterpart": "10-24"}
    assert size_bucket(9) == "1-9" and size_bucket(50) == "50+"


def _pkg(results):
    return {"request_id": "r", "ticket_id": "t", "producer_id": "persona_a", "consumer_id": "persona_a",
            "counterpart_id": "persona_b", "scope": {}, "policy_version": 1, "method": "m",
            "algorithm_version": "v", "input_provenance": {}, "created_at": "x", "results": results,
            "disclosed_to_counterpart": {}}


@pytest.mark.parametrize("results,disclosure,ok", [
    ({"Protein": {"band": "high"}}, "score_only", True),
    ({"Protein": {"band": "high", "set_size_buckets": {"own": "1-9"}}}, "score_only", False),
    ({"Protein": {"band": "high", "set_size_buckets": {"own": "1-9"}}}, "summary", True),
    ({"Protein": {"band": "high", "intersection": 12}}, "summary", False),
    ({"Protein": {"band": 0.46}}, "score_only", False),
    ({"Protein": {"band": "high"}}, "evidence", False),
])
def test_package_violations(results, disclosure, ok):
    assert (package_violations(_pkg(results), disclosure) == []) is ok


def test_package_extra_top_level_field_rejected():
    assert "field:matched_ids" in package_violations({**_pkg({}), "matched_ids": ["P04637"]}, "summary")


def test_package_signature(keys):
    signed = sign_package(keys[0]["persona_a"], _pkg({"Protein": {"band": "low"}}))
    assert verify_package(signed, keys[1].get("persona_a"))["results"]["Protein"]["band"] == "low"
    with pytest.raises(AuthError):
        verify_package(signed, keys[1].get("persona_b"))
