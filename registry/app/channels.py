"""Discovery channels: owner-controlled, topics-only, 24-hour lifetime.

State machine: DRAFT -> ACTIVE <-> PAUSED; ACTIVE|PAUSED -> CLOSED; ACTIVE|PAUSED -> EXPIRED.
Expiry is derived from `expires_at` against the registry clock on every read and action, so it
holds even before the stored status is reconciled. Pause never extends `expires_at`.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from similarity.public_topics import topic_similarity

from .audit import record
from .clock import Clock, as_utc
from .config import Settings
from .deps import get_clock, get_db, get_settings, problem, verified_researcher
from .models import Channel, ChannelPolicyVersion, Researcher

router = APIRouter(prefix="/v1/channels")

LIVE = ("ACTIVE", "PAUSED")
TRANSITIONS = {
    "activate": ({"DRAFT"}, "ACTIVE"),
    "pause": ({"ACTIVE"}, "PAUSED"),
    "resume": ({"PAUSED"}, "ACTIVE"),
    "close": ({"ACTIVE", "PAUSED"}, "CLOSED"),
}


def effective_status(ch: Channel, now: datetime) -> str:
    if ch.status in LIVE and ch.expires_at is not None and now >= as_utc(ch.expires_at):
        return "EXPIRED"
    return ch.status


def reconcile_expired(db: Session, clock: Clock) -> None:
    """Persist EXPIRED for live channels past their deadline (bookkeeping; checks never rely on it)."""
    now = clock.now()
    for ch in db.scalars(select(Channel).where(Channel.status.in_(LIVE))).all():
        if effective_status(ch, now) == "EXPIRED":
            ch.status, ch.updated_at = "EXPIRED", now
            record(db, clock, actor_id=None, action="channel.expire", object_type="channel", object_id=ch.id,
                   policy_version=ch.policy_version, reason_code="lifetime_elapsed")
    db.commit()


def owner_view(ch: Channel, now: datetime) -> dict:
    return {"id": ch.id, "owner_id": ch.owner_id, "topics": ch.topics, "audience": ch.audience,
            "visibility": ch.visibility, "approval_mode": ch.approval_mode,
            "status": effective_status(ch, now), "activated_at": _iso(ch.activated_at),
            "expires_at": _iso(ch.expires_at), "policy_version": ch.policy_version,
            "created_at": _iso(ch.created_at)}


def discovery_view(ch: Channel, owner: Researcher, viewer: Researcher) -> dict:
    """What a verified non-owner may see: published topics only, never graph content."""
    return {"id": ch.id, "owner": {"researcher_id": owner.id, "display_name": owner.display_name},
            "topics": ch.topics, "visibility": ch.visibility, "approval_mode": ch.approval_mode,
            "expires_at": _iso(ch.expires_at),
            "topic_match": topic_similarity(set(viewer.published_topics), set(ch.topics))}


def _iso(dt: datetime | None) -> str | None:
    return as_utc(dt).isoformat() if dt else None


def _deny(db: Session, clock: Clock, me: Researcher, action: str, ch_id: str, status: int, code: str,
          message: str, policy_version: int | None = None):
    record(db, clock, actor_id=me.id, action=action, object_type="channel", object_id=ch_id,
           decision="deny", reason_code=code, policy_version=policy_version)
    db.commit()
    return problem(status, code, message)


def _locked_owned(db: Session, clock: Clock, me: Researcher, channel_id: str, action: str) -> Channel:
    ch = db.execute(select(Channel).where(Channel.id == channel_id).with_for_update()).scalar_one_or_none()
    if ch is None:
        raise _deny(db, clock, me, action, channel_id, 404, "channel_not_found", "no such channel")
    if ch.owner_id != me.id:
        raise _deny(db, clock, me, action, channel_id, 403, "not_owner", "only the owner may change this channel")
    return ch


def _validate_topics(me: Researcher, topics: list[str]) -> list[str]:
    unique = sorted(set(topics))
    unpublished = [t for t in unique if t not in me.published_topics]
    if unpublished:
        raise problem(422, "topic_not_published",
                      f"channel topics must be an opt-in subset of your published topics: {unpublished}")
    return unique


def _snapshot(db: Session, ch: Channel, actor: Researcher, now: datetime) -> None:
    db.add(ChannelPolicyVersion(channel_id=ch.id, version=ch.policy_version, topics=ch.topics,
                                audience=ch.audience, visibility=ch.visibility,
                                approval_mode=ch.approval_mode, created_by=actor.id, created_at=now))


class ChannelCreate(BaseModel):
    # extra="forbid": a client-supplied owner_id (or anything else) is rejected, never trusted.
    model_config = ConfigDict(extra="forbid")
    topics: list[str] = Field(min_length=1)


class ChannelPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topics: list[str] = Field(min_length=1)
    expected_policy_version: int


@router.post("", status_code=201)
def create_channel(body: ChannelCreate, me: Researcher = Depends(verified_researcher),
                   db: Session = Depends(get_db), clock: Clock = Depends(get_clock)) -> dict:
    now = clock.now()
    ch = Channel(owner_id=me.id, topics=_validate_topics(me, body.topics), status="DRAFT",
                 policy_version=1, created_at=now, updated_at=now)
    db.add(ch)
    db.flush()
    _snapshot(db, ch, me, now)
    record(db, clock, actor_id=me.id, action="channel.create", object_type="channel", object_id=ch.id,
           policy_version=1)
    db.commit()
    return owner_view(ch, now)


@router.get("")
def discover(me: Researcher = Depends(verified_researcher), db: Session = Depends(get_db),
             clock: Clock = Depends(get_clock)) -> dict:
    """Active, unexpired, verified-audience channels of other researchers, ranked by topic match."""
    reconcile_expired(db, clock)
    now = clock.now()
    rows = db.execute(select(Channel, Researcher).join(Researcher, Channel.owner_id == Researcher.id)
                      .where(Channel.status == "ACTIVE", Channel.owner_id != me.id,
                             Channel.audience == "verified_researchers")).all()
    items = [discovery_view(ch, owner, me) for ch, owner in rows if effective_status(ch, now) == "ACTIVE"]
    items.sort(key=lambda c: (-c["topic_match"]["score"], c["expires_at"] or "", c["id"]))
    return {"channels": items}


@router.get("/mine")
def my_channels(me: Researcher = Depends(verified_researcher), db: Session = Depends(get_db),
                clock: Clock = Depends(get_clock)) -> dict:
    reconcile_expired(db, clock)
    now = clock.now()
    rows = db.scalars(select(Channel).where(Channel.owner_id == me.id).order_by(Channel.created_at)).all()
    return {"channels": [owner_view(ch, now) for ch in rows]}


@router.get("/{channel_id}")
def get_channel(channel_id: str, me: Researcher = Depends(verified_researcher), db: Session = Depends(get_db),
                clock: Clock = Depends(get_clock)) -> dict:
    now = clock.now()
    ch = db.get(Channel, channel_id)
    if ch is not None and ch.owner_id == me.id:
        return owner_view(ch, now)
    # Non-owners see only discoverable channels; anything else is indistinguishable from absent.
    if ch is None or effective_status(ch, now) != "ACTIVE" or ch.audience != "verified_researchers":
        raise problem(404, "channel_not_found", "no such channel")
    return discovery_view(ch, db.get(Researcher, ch.owner_id), me)


@router.patch("/{channel_id}")
def update_channel(channel_id: str, body: ChannelPatch, me: Researcher = Depends(verified_researcher),
                   db: Session = Depends(get_db), clock: Clock = Depends(get_clock)) -> dict:
    ch = _locked_owned(db, clock, me, channel_id, "channel.update")
    now = clock.now()
    status = effective_status(ch, now)
    if status in ("EXPIRED", "CLOSED"):
        raise _deny(db, clock, me, "channel.update", ch.id, 409, f"channel_{status.lower()}",
                    f"channel is {status.lower()}", ch.policy_version)
    if body.expected_policy_version != ch.policy_version:
        raise _deny(db, clock, me, "channel.update", ch.id, 409, "stale_policy_version",
                    f"channel is at policy version {ch.policy_version}", ch.policy_version)
    ch.topics = _validate_topics(me, body.topics)
    ch.policy_version += 1
    ch.updated_at = now
    _snapshot(db, ch, me, now)
    record(db, clock, actor_id=me.id, action="channel.update", object_type="channel", object_id=ch.id,
           policy_version=ch.policy_version)
    db.commit()
    return owner_view(ch, now)


def _transition(action: str):
    allowed, target = TRANSITIONS[action]

    def endpoint(channel_id: str, me: Researcher = Depends(verified_researcher), db: Session = Depends(get_db),
                 clock: Clock = Depends(get_clock), settings: Settings = Depends(get_settings)) -> dict:
        ch = _locked_owned(db, clock, me, channel_id, f"channel.{action}")
        now = clock.now()
        status = effective_status(ch, now)
        if status == "EXPIRED":
            ch.status = "EXPIRED"
            raise _deny(db, clock, me, f"channel.{action}", ch.id, 409, "channel_expired",
                        "channel has expired", ch.policy_version)
        if status not in allowed:
            raise _deny(db, clock, me, f"channel.{action}", ch.id, 409, "invalid_transition",
                        f"cannot {action} a {status.lower()} channel", ch.policy_version)
        if action == "activate":
            ch.activated_at = now
            ch.expires_at = now + timedelta(seconds=settings.channel_lifetime_seconds)
        ch.status, ch.updated_at = target, now
        record(db, clock, actor_id=me.id, action=f"channel.{action}", object_type="channel", object_id=ch.id,
               policy_version=ch.policy_version)
        db.commit()
        return owner_view(ch, now)

    endpoint.__name__ = f"{action}_channel"
    return endpoint


for _action in TRANSITIONS:
    router.add_api_route(f"/{{channel_id}}/{_action}", _transition(_action), methods=["POST"])
