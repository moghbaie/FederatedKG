"""User session tokens issued by the registry (EdDSA), verifiable by any agent holding the keyring.

Agents use this only for the owner's own "My KG" view: subject must equal the agent's persona.
"""
from __future__ import annotations

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .tokens import AuthError

USER_TOKEN_TYPE = "fkg-user"
USER_ISSUER = "fkg-registry"
USER_AUDIENCE = "fkg-web"


def sign_user_token(key: Ed25519PrivateKey, claims: dict) -> str:
    return jwt.encode({**claims, "iss": USER_ISSUER, "aud": USER_AUDIENCE}, key, algorithm="EdDSA",
                      headers={"typ": USER_TOKEN_TYPE})


def verify_user_token(token: str, registry_key: Ed25519PublicKey, now: float) -> dict:
    try:
        if jwt.get_unverified_header(token).get("typ") != USER_TOKEN_TYPE:
            raise AuthError("not_a_user_token")
        claims = jwt.decode(token, registry_key, algorithms=["EdDSA"], audience=USER_AUDIENCE, issuer=USER_ISSUER,
                            options={"verify_exp": False, "verify_iat": False,
                                     "require": ["sub", "exp", "iat", "jti"]})
    except AuthError:
        raise
    except jwt.PyJWTError:
        raise AuthError("invalid_user_token") from None
    if now >= claims["exp"]:
        raise AuthError("user_token_expired")
    return claims
