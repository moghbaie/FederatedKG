"""Comparison tickets: registry-signed, short-lived, single-use authorizations for one comparison.

A ticket binds the request, both participants, protocol, canonical scope, approved policy version
and result recipients. Agents verify it independently and still apply their own local policy.
"""
from __future__ import annotations

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .tokens import LEEWAY_SECONDS, AuthError

TICKET_TTL_SECONDS = 300
TICKET_ISSUER = "registry"
TICKET_FIELDS = ("jti", "request_id", "requester_id", "recipient_id", "protocol", "scope", "scope_fingerprint",
                 "result_recipients", "iat", "exp")
# Present but null for targeted (one-to-one) requests; PyJWT's `require` treats null as missing.
NULLABLE_TICKET_FIELDS = ("channel_id", "policy_version")


def issue_ticket(key: Ed25519PrivateKey, claims: dict, now: float) -> str:
    body = {**claims, "iss": TICKET_ISSUER, "iat": int(now), "exp": int(now) + TICKET_TTL_SECONDS}
    return jwt.encode(body, key, algorithm="EdDSA", headers={"typ": "fkg-ticket"})


def verify_ticket(token: str, registry_key: Ed25519PublicKey, now: float) -> dict:
    try:
        if jwt.get_unverified_header(token).get("typ") != "fkg-ticket":
            raise AuthError("not_a_ticket")
        claims = jwt.decode(token, registry_key, algorithms=["EdDSA"], issuer=TICKET_ISSUER,
                            options={"verify_exp": False, "verify_iat": False, "verify_aud": False,
                                     "require": list(TICKET_FIELDS)})
    except AuthError:
        raise
    except jwt.PyJWTError:
        raise AuthError("invalid_ticket") from None
    if any(f not in claims for f in NULLABLE_TICKET_FIELDS):
        raise AuthError("invalid_ticket")
    if not (claims["iat"] - LEEWAY_SECONDS <= now <= claims["exp"]):
        raise AuthError("ticket_expired")
    if set(claims["result_recipients"]) - {claims["requester_id"], claims["recipient_id"]}:
        raise AuthError("ticket_recipients_invalid")
    return claims


def counterpart(ticket: dict, me: str) -> str:
    if me == ticket["requester_id"]:
        return ticket["recipient_id"]
    if me == ticket["recipient_id"]:
        return ticket["requester_id"]
    raise AuthError("not_a_participant")
