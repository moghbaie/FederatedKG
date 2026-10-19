"""Request-scoped dependencies: database session, clock, authenticated researcher."""
from __future__ import annotations

from collections.abc import Iterator

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from fkg_protocol.tokens import AuthError
from fkg_protocol.users import verify_user_token

from .audit import record
from .clock import Clock
from .config import Settings
from .models import Researcher

TOKEN_ISSUER = "fkg-registry"
TOKEN_AUDIENCE = "fkg-web"

_bearer = HTTPBearer(auto_error=False)


def problem(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.sessionmaker() as session:
        yield session


def current_researcher(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
) -> Researcher:
    if creds is None:
        raise problem(401, "unauthenticated", "missing bearer token")
    # Expiry is checked against the registry clock (not the library's wall clock) so that
    # test-clock advances expire tokens consistently with channels.
    identity = request.app.state.identity
    if identity.available:
        # Exactly one algorithm is accepted per deployment, so tokens cannot be downgraded to HS256.
        try:
            claims = verify_user_token(creds.credentials, identity.keyring.get("registry"),
                                       clock.now().timestamp())
        except AuthError as e:
            code = "token_expired" if e.code == "user_token_expired" else "invalid_token"
            raise problem(401, code, "token is invalid or expired") from None
    else:
        try:
            claims = jwt.decode(creds.credentials, settings.token_secret, algorithms=["HS256"],
                                audience=TOKEN_AUDIENCE, issuer=TOKEN_ISSUER,
                                options={"verify_exp": False, "verify_iat": False,
                                         "require": ["sub", "exp", "iat", "jti"]})
        except jwt.PyJWTError:
            raise problem(401, "invalid_token", "token is invalid") from None
        if clock.now().timestamp() >= claims["exp"]:
            raise problem(401, "token_expired", "token has expired")
    researcher = db.get(Researcher, claims["sub"])
    if researcher is None:
        raise problem(401, "invalid_token", "unknown subject")
    return researcher


def verified_researcher(
    me: Researcher = Depends(current_researcher),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Researcher:
    if not me.verified_researcher:
        record(db, clock, actor_id=me.id, action="access.verified_only", object_type="researcher",
               object_id=me.id, decision="deny", reason_code="unverified_researcher")
        db.commit()
        raise problem(403, "unverified_researcher", "this action requires a verified research account")
    return me
