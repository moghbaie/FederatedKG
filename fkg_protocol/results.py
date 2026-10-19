"""Result packages: disclosure shaping, coarse bands, and producer signatures.

Exact intersection counts never leave the output party's agent. A package carries only the fields
its disclosure level permits; the registry rejects any package with extra fields.
"""
from __future__ import annotations

import json

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .tokens import AuthError

LOW_COUNT_THRESHOLD = 3
JACCARD_BANDS = ((0.2, "low"), (0.4, "medium"))  # below 0.2 low, below 0.4 medium, else high
COUNT_BANDS = ((6, "low"), (10, "medium"))        # 3-5 low, 6-9 medium, 10+ high
SIZE_BUCKETS = ((10, "1-9"), (25, "10-24"), (50, "25-49"))

ALLOWED_RESULT_FIELDS = {
    "score_only": {"band"},
    "summary": {"band", "set_size_buckets"},
}
PACKAGE_FIELDS = {"request_id", "ticket_id", "producer_id", "consumer_id", "counterpart_id", "scope",
                  "policy_version", "method", "algorithm_version", "input_provenance", "created_at", "results",
                  "disclosed_to_counterpart"}


def band(metric: str, intersection: int, union: int) -> str:
    """Coarse similarity band. A display policy: the output agent itself saw the exact count."""
    if intersection < LOW_COUNT_THRESHOLD:
        return "insufficient_disclosure"
    if metric == "jaccard":
        value = intersection / union if union else 0.0
        bands = JACCARD_BANDS
    else:
        value = intersection
        bands = COUNT_BANDS
    for limit, name in bands:
        if value < limit:
            return name
    return "high"


def size_bucket(n: int) -> str:
    for limit, name in SIZE_BUCKETS:
        if n < limit:
            return name
    return "50+"


def shape(disclosure: str, metric: str, intersection: int, own_size: int, other_size: int) -> dict:
    out = {"band": band(metric, intersection, own_size + other_size - intersection)}
    if disclosure == "summary":
        out["set_size_buckets"] = {"own": size_bucket(own_size), "counterpart": size_bucket(other_size)}
    return out


def sign_package(key: Ed25519PrivateKey, package: dict) -> str:
    return jwt.encode({"pkg": package}, key, algorithm="EdDSA", headers={"typ": "fkg-result"})


def verify_package(signed: str, producer_key: Ed25519PublicKey) -> dict:
    try:
        if jwt.get_unverified_header(signed).get("typ") != "fkg-result":
            raise AuthError("not_a_result_package")
        return jwt.decode(signed, producer_key, algorithms=["EdDSA"], options={"verify_aud": False})["pkg"]
    except AuthError:
        raise
    except jwt.PyJWTError:
        raise AuthError("invalid_result_signature") from None


def package_violations(package: dict, disclosure: str) -> list[str]:
    """Fields beyond what the disclosure level authorizes (must be empty to release)."""
    problems = [f"field:{k}" for k in set(package) - PACKAGE_FIELDS]
    allowed = ALLOWED_RESULT_FIELDS.get(disclosure, set())
    for cls, result in package.get("results", {}).items():
        problems += [f"result:{cls}:{k}" for k in set(result) - allowed]
        if "band" in result and not isinstance(result["band"], str):
            problems.append(f"result:{cls}:band_type")
    if any(isinstance(v, int) and not isinstance(v, bool) for v in _walk(package.get("results", {}))):
        problems.append("results:numeric_value")  # exact counts or scores must never be released
    return problems


def _walk(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)
    else:
        yield obj


def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
