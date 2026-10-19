"""Demo identities and researcher directory.

The demo login is a clearly labelled stand-in for OIDC: it issues short-lived, server-signed
tokens for the five simulated accounts. Identity is only ever taken from the token.
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta

import jwt
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from fkg_protocol.users import sign_user_token
from similarity.public_topics import topic_similarity

from .audit import record
from .clock import Clock
from .config import Settings
from .deps import (TOKEN_AUDIENCE, TOKEN_ISSUER, current_researcher, get_clock, get_db, get_settings,
                   problem, verified_researcher)
from .models import Researcher

router = APIRouter(prefix="/v1")


def seed_researchers(db: Session, settings: Settings) -> None:
    """Upsert public profiles from the fixture file (idempotent)."""
    data = json.loads(settings.public_profiles.read_text(encoding="utf-8"))
    for r in data["researchers"]:
        row = db.get(Researcher, r["researcher_id"]) or Researcher(id=r["researcher_id"])
        row.display_name = r["display_name"]
        row.theme = r["theme"]
        row.verified_researcher = r["verified_researcher"]
        row.published_topics = list(r["published_topics"])
        row.topic_vocabulary = r["topic_vocabulary"]
        row.inspiration = r["public_scientific_inspiration"]
        row.is_simulated = r["is_simulated"]
        db.add(row)
    db.commit()


def profile(r: Researcher) -> dict:
    return {"researcher_id": r.id, "display_name": r.display_name, "theme": r.theme,
            "verified_researcher": r.verified_researcher, "published_topics": r.published_topics,
            "is_simulated": r.is_simulated, "public_scientific_inspiration": r.inspiration}


class DemoLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    researcher_id: str


@router.post("/auth/demo-login")
def demo_login(body: DemoLogin, request: Request, db: Session = Depends(get_db),
               settings: Settings = Depends(get_settings), clock: Clock = Depends(get_clock)) -> dict:
    researcher = db.get(Researcher, body.researcher_id)
    if researcher is None:
        raise problem(401, "unknown_account", "no such demo account")
    now = clock.now()
    expires = now + timedelta(seconds=settings.token_ttl_seconds)
    claims = {"sub": researcher.id, "iat": int(now.timestamp()), "exp": int(expires.timestamp()),
              "jti": str(uuid.uuid4())}
    identity = request.app.state.identity
    if identity.available:
        # EdDSA: agents can verify it (owner-only "My KG" view) with the public keyring.
        token = sign_user_token(identity.key, claims)
    else:
        token = jwt.encode({**claims, "iss": TOKEN_ISSUER, "aud": TOKEN_AUDIENCE}, settings.token_secret,
                           algorithm="HS256")
    record(db, clock, actor_id=researcher.id, action="auth.demo_login", object_type="researcher",
           object_id=researcher.id)
    db.commit()
    return {"access_token": token, "token_type": "bearer", "expires_at": expires.isoformat(),
            "demo_login": True, "researcher": profile(researcher)}


@router.get("/me")
def me(researcher: Researcher = Depends(current_researcher)) -> dict:
    return profile(researcher)


@router.get("/researchers")
def directory(me: Researcher = Depends(verified_researcher), db: Session = Depends(get_db)) -> dict:
    """Verified researchers other than the caller, ranked by published-topic similarity."""
    others = db.scalars(select(Researcher).where(Researcher.verified_researcher.is_(True),
                                                 Researcher.id != me.id)).all()
    entries = [{**profile(r), "topic_match": topic_similarity(set(me.published_topics), set(r.published_topics))}
               for r in others]
    entries.sort(key=lambda e: (-e["topic_match"]["score"], e["researcher_id"]))
    return {"researchers": entries}
