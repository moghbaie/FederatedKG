"""Short-lived service tokens (EdDSA JWT) bound to caller, audience, method, path and body hash.

A token proves *which service* sent *this exact request*; the receiver rejects replays by jti.
"""
from __future__ import annotations

import hashlib
import threading
import time
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .keys import Keyring

TOKEN_TTL_SECONDS = 60
LEEWAY_SECONDS = 5


class AuthError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def sign_service_token(key: Ed25519PrivateKey, issuer: str, audience: str, method: str, path: str,
                       body: bytes, now: float) -> str:
    claims = {"iss": issuer, "aud": audience, "iat": int(now), "exp": int(now) + TOKEN_TTL_SECONDS,
              "jti": uuid.uuid4().hex, "htm": method.upper(), "htu": path, "bh": body_hash(body)}
    return jwt.encode(claims, key, algorithm="EdDSA", headers={"typ": "fkg-service"})


class ReplayCache:
    def __init__(self):
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def check_and_add(self, jti: str, exp: float, now: float) -> bool:
        with self._lock:
            for k in [k for k, e in self._seen.items() if e + LEEWAY_SECONDS < now]:
                del self._seen[k]
            if jti in self._seen:
                return False
            self._seen[jti] = exp
            return True


def verify_service_token(token: str | None, keyring: Keyring, audience: str, method: str, path: str,
                         body: bytes, replay: ReplayCache, now: float,
                         allowed_issuers: tuple[str, ...] | None = None) -> dict:
    if not token:
        raise AuthError("missing_service_token")
    try:
        header = jwt.get_unverified_header(token)
        unverified = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        raise AuthError("malformed_service_token") from None
    if header.get("typ") != "fkg-service" or header.get("alg") != "EdDSA":
        raise AuthError("wrong_token_type")
    issuer = unverified.get("iss")
    if allowed_issuers is not None and issuer not in allowed_issuers:
        raise AuthError("issuer_not_allowed")
    public = keyring.get(issuer) if isinstance(issuer, str) else None
    if public is None:
        raise AuthError("unknown_issuer")
    try:
        claims = jwt.decode(token, public, algorithms=["EdDSA"], audience=audience,
                            options={"verify_exp": False, "verify_iat": False,
                                     "require": ["iss", "aud", "iat", "exp", "jti", "htm", "htu", "bh"]})
    except jwt.PyJWTError:
        raise AuthError("invalid_service_token") from None
    if not (claims["iat"] - LEEWAY_SECONDS <= now <= claims["exp"] + LEEWAY_SECONDS):
        raise AuthError("service_token_expired")
    if claims["htm"] != method.upper() or claims["htu"] != path:
        raise AuthError("token_request_mismatch")
    if claims["bh"] != body_hash(body):
        raise AuthError("body_hash_mismatch")
    if not replay.check_and_add(claims["jti"], claims["exp"], now):
        raise AuthError("replayed_service_token")
    return claims


def wall_now() -> float:
    return time.time()
