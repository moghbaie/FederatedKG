"""Comparison requests: open-channel and targeted one-to-one, with manual approval.

Every transition takes row locks (channel first, then request) and re-checks effective status and
current policy, so approvals, policy edits and closures serialize cleanly. Approval to compare
never authorizes sharing graph data; no comparison runs here (Phase 4 consumes `execution_check`).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .audit import record
from .clock import Clock, as_utc
from .config import Settings
from .deps import get_clock, get_db, get_settings, problem, verified_researcher
from .models import Channel, ComparisonRequest, Researcher
from .notifications import notify
from .policy import Policy, Scope, fingerprint, incompatibility
from .status import OPEN_REQUEST, channel_policy, channel_status, request_status, targeted_policy

router = APIRouter(prefix="/v1")


class RequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Scope
    result_visibility: Literal["requester_only", "both"] = "requester_only"
    idempotency_key: str = Field(min_length=8, max_length=128)


# ---- shared helpers (also used by channel lifecycle) ---------------------------------------------

def _set_status(db: Session, clock: Clock, req: ComparisonRequest, status: str, reason: str | None,
                actor_id: str | None, action: str, notify_ids: list[str], kind: str,
                policy_version: int | None = None) -> None:
    now = clock.now()
    req.status, req.status_reason, req.updated_at = status, reason, now
    if status in ("APPROVED", "REJECTED"):
        req.decision_at = now
    record(db, clock, actor_id=actor_id, action=action, object_type="request", object_id=req.id,
           reason_code=reason, policy_version=policy_version)
    for rid in notify_ids:
        notify(db, clock, rid, kind, req.id)


def _open_channel_requests(db: Session, channel_id: str) -> list[ComparisonRequest]:
    return list(db.scalars(select(ComparisonRequest).where(ComparisonRequest.channel_id == channel_id,
                                                           ComparisonRequest.status.in_(OPEN_REQUEST))
                           .order_by(ComparisonRequest.id).with_for_update()).all())


def cancel_open_requests(db: Session, clock: Clock, ch: Channel, reason: str, actor_id: str) -> None:
    """Channel closed: unfinished requests are cancelled (prior disclosures cannot be undone)."""
    for req in _open_channel_requests(db, ch.id):
        _set_status(db, clock, req, "CANCELLED", reason, actor_id, "request.cancel",
                    [req.requester_id, req.recipient_id], "request_cancelled", ch.policy_version)


def revalidate_open_requests(db: Session, clock: Clock, ch: Channel, actor_id: str) -> None:
    """Policy changed: open requests that no longer fit the new version are invalidated."""
    policy = channel_policy(ch)
    for req in _open_channel_requests(db, ch.id):
        why = incompatibility(req.requested_scope, req.result_visibility, policy)
        if why:
            _set_status(db, clock, req, "CANCELLED", "policy_incompatible", actor_id, "request.invalidate",
                        [req.requester_id, req.recipient_id], "request_invalidated", ch.policy_version)


def reconcile_requests(db: Session, clock: Clock) -> None:
    """Persist EXPIRED for open requests past their deadline (bookkeeping only)."""
    now = clock.now()
    for req in db.scalars(select(ComparisonRequest).where(ComparisonRequest.status.in_(OPEN_REQUEST))).all():
        ch = db.get(Channel, req.channel_id) if req.channel_id else None
        if request_status(req, ch, now) == "EXPIRED":
            _set_status(db, clock, req, "EXPIRED", "lifetime_elapsed", None, "request.expire",
                        [req.requester_id, req.recipient_id], "request_expired")
    db.commit()


def execution_check(db: Session, req: ComparisonRequest, now: datetime) -> dict:
    """Would a comparison be allowed to run right now? Re-evaluated at execution and release."""
    ch = db.get(Channel, req.channel_id) if req.channel_id else None
    status = request_status(req, ch, now)
    if status != "APPROVED":
        return {"ok": False, "reason": f"request_{status.lower()}"}
    if ch is not None:
        if channel_status(ch, now) != "ACTIVE":
            return {"ok": False, "reason": f"channel_{channel_status(ch, now).lower()}"}
        why = incompatibility(req.requested_scope, req.result_visibility, channel_policy(ch))
        if why:
            return {"ok": False, "reason": why}
    else:
        recipient = db.get(Researcher, req.recipient_id)
        if not recipient.verified_researcher:
            return {"ok": False, "reason": "recipient_not_verified"}
    return {"ok": True, "reason": None}


def view(db: Session, req: ComparisonRequest, now: datetime) -> dict:
    ch = db.get(Channel, req.channel_id) if req.channel_id else None
    names = {r.id: r.display_name for r in db.scalars(
        select(Researcher).where(Researcher.id.in_([req.requester_id, req.recipient_id])))}
    out = {"id": req.id, "kind": "channel" if req.channel_id else "targeted", "channel_id": req.channel_id,
           "requester": {"researcher_id": req.requester_id, "display_name": names[req.requester_id]},
           "recipient": {"researcher_id": req.recipient_id, "display_name": names[req.recipient_id]},
           "requested_scope": req.requested_scope, "result_visibility": req.result_visibility,
           "status": request_status(req, ch, now), "status_reason": req.status_reason,
           "created_at": as_utc(req.created_at).isoformat(),
           "decision_at": as_utc(req.decision_at).isoformat() if req.decision_at else None,
           "approved_policy_version": req.approved_policy_version,
           "expires_at": as_utc(req.expires_at).isoformat()}
    if out["status"] == "APPROVED":
        out["execution_check"] = execution_check(db, req, now)
    return out


# ---- creation ---------------------------------------------------------------------------------

def _deny(db: Session, clock: Clock, me: Researcher, object_type: str, object_id: str | None, status: int,
          code: str, message: str, extra: dict | None = None):
    record(db, clock, actor_id=me.id, action="request.create", object_type=object_type, object_id=object_id,
           decision="deny", reason_code=code)
    db.commit()
    exc = problem(status, code, message)
    if extra:
        exc.detail.update(extra)
    return exc


def _create(body: RequestCreate, me: Researcher, recipient: Researcher, policy: Policy, expires_at: datetime,
            channel: Channel | None, db: Session, clock: Clock, settings: Settings, response: Response) -> dict:
    now = clock.now()
    scope = body.scope.canonical()
    fp = fingerprint(scope)
    target_type, target_id = ("channel", channel.id) if channel else ("researcher", recipient.id)

    # Serialize this requester's submissions so duplicate and quota checks cannot race.
    db.execute(select(Researcher).where(Researcher.id == me.id).with_for_update())

    existing = db.scalars(select(ComparisonRequest).where(ComparisonRequest.requester_id == me.id,
                                                          ComparisonRequest.idempotency_key == body.idempotency_key)
                          ).one_or_none()
    if existing is not None:
        same = (existing.channel_id == (channel.id if channel else None) and existing.recipient_id == recipient.id
                and existing.scope_fingerprint == fp and existing.result_visibility == body.result_visibility)
        if not same:
            raise _deny(db, clock, me, target_type, target_id, 409, "idempotency_conflict",
                        "idempotency key was already used for a different request")
        response.status_code = 200
        return view(db, existing, now)

    if scope["disclosure"] == "evidence":
        raise _deny(db, clock, me, target_type, target_id, 403, "evidence_disabled",
                    "evidence sharing is not available in v1 and is never granted by a comparison request")
    if scope["protocol"] == "plaintext_dev" and not settings.dev_plaintext_matcher:
        raise _deny(db, clock, me, target_type, target_id, 422, "protocol_not_enabled",
                    "plaintext_dev is a development-only matcher and is disabled")
    why = incompatibility(scope, body.result_visibility, policy)
    if why:
        raise _deny(db, clock, me, target_type, target_id, 422, why, "requested scope does not fit the policy")

    pair = select(ComparisonRequest).where(ComparisonRequest.requester_id == me.id,
                                           ComparisonRequest.recipient_id == recipient.id)
    for other in db.scalars(pair.where(ComparisonRequest.scope_fingerprint == fp,
                                       ComparisonRequest.status.in_(OPEN_REQUEST))).all():
        other_ch = db.get(Channel, other.channel_id) if other.channel_id else None
        if other.channel_id == (channel.id if channel else None) and \
                request_status(other, other_ch, now) in ("PENDING", "APPROVED"):
            raise _deny(db, clock, me, target_type, target_id, 409, "duplicate_open_request",
                        "an identical request is already open", {"existing_request_id": other.id})

    recent = db.scalars(pair.where(ComparisonRequest.created_at >= now - timedelta(hours=24))).all()
    if len(recent) >= settings.pair_request_limit:
        raise _deny(db, clock, me, target_type, target_id, 429, "rate_limited",
                    "too many requests to this researcher in the last 24 hours")
    if len({r.scope_fingerprint for r in recent} | {fp}) > settings.pair_distinct_scope_limit:
        raise _deny(db, clock, me, target_type, target_id, 429, "scope_quota_exceeded",
                    "too many distinct scopes requested from this researcher in the last 24 hours")

    req = ComparisonRequest(channel_id=channel.id if channel else None,
                            target_researcher_id=None if channel else recipient.id,
                            requester_id=me.id, recipient_id=recipient.id, requested_scope=scope,
                            scope_fingerprint=fp, result_visibility=body.result_visibility, status="PENDING",
                            created_at=now, updated_at=now, expires_at=expires_at,
                            idempotency_key=body.idempotency_key)
    db.add(req)
    db.flush()
    record(db, clock, actor_id=me.id, action="request.create", object_type="request", object_id=req.id,
           policy_version=channel.policy_version if channel else None)
    notify(db, clock, recipient.id, "request_received", req.id)
    db.commit()
    response.status_code = 201
    return view(db, req, now)


@router.post("/channels/{channel_id}/requests", status_code=201)
def request_via_channel(channel_id: str, body: RequestCreate, response: Response,
                        me: Researcher = Depends(verified_researcher), db: Session = Depends(get_db),
                        clock: Clock = Depends(get_clock), settings: Settings = Depends(get_settings)) -> dict:
    # Lock the channel so a concurrent policy edit or closure cannot miss this request.
    ch = db.execute(select(Channel).where(Channel.id == channel_id).with_for_update()).scalar_one_or_none()
    if ch is None or ch.status == "DRAFT":
        raise _deny(db, clock, me, "channel", channel_id, 404, "channel_not_found", "no such channel")
    if ch.owner_id == me.id:
        raise _deny(db, clock, me, "channel", ch.id, 422, "own_channel", "cannot request a comparison with yourself")
    status = channel_status(ch, clock.now())
    if status == "EXPIRED":
        raise _deny(db, clock, me, "channel", ch.id, 409, "channel_expired", "channel has expired")
    if status != "ACTIVE":
        raise _deny(db, clock, me, "channel", ch.id, 409, "channel_not_accepting_requests",
                    f"channel is {status.lower()}")
    owner = db.get(Researcher, ch.owner_id)
    return _create(body, me, owner, channel_policy(ch), as_utc(ch.expires_at), ch, db, clock, settings, response)


@router.post("/researchers/{researcher_id}/requests", status_code=201)
def request_targeted(researcher_id: str, body: RequestCreate, response: Response,
                     me: Researcher = Depends(verified_researcher), db: Session = Depends(get_db),
                     clock: Clock = Depends(get_clock), settings: Settings = Depends(get_settings)) -> dict:
    recipient = db.get(Researcher, researcher_id)
    if recipient is None or not recipient.verified_researcher:
        raise _deny(db, clock, me, "researcher", researcher_id, 404, "researcher_not_found", "no such researcher")
    if recipient.id == me.id:
        raise _deny(db, clock, me, "researcher", me.id, 422, "own_profile", "cannot request a comparison with yourself")
    expires = clock.now() + timedelta(seconds=settings.targeted_request_ttl_seconds)
    return _create(body, me, recipient, targeted_policy(recipient), expires, None, db, clock, settings, response)


# ---- reading ----------------------------------------------------------------------------------

@router.get("/requests/inbox")
def inbox(status: str | None = None, me: Researcher = Depends(verified_researcher), db: Session = Depends(get_db),
          clock: Clock = Depends(get_clock)) -> dict:
    reconcile_requests(db, clock)
    now = clock.now()
    rows = db.scalars(select(ComparisonRequest).where(ComparisonRequest.recipient_id == me.id)
                      .order_by(ComparisonRequest.created_at, ComparisonRequest.id)).all()
    items = [view(db, r, now) for r in rows]
    return {"requests": [i for i in items if status is None or i["status"] == status.upper()]}


@router.get("/requests/outbox")
def outbox(me: Researcher = Depends(verified_researcher), db: Session = Depends(get_db),
           clock: Clock = Depends(get_clock)) -> dict:
    reconcile_requests(db, clock)
    now = clock.now()
    rows = db.scalars(select(ComparisonRequest).where(ComparisonRequest.requester_id == me.id)
                      .order_by(ComparisonRequest.created_at, ComparisonRequest.id)).all()
    return {"requests": [view(db, r, now) for r in rows]}


def _party_request(db: Session, me: Researcher, request_id: str, lock: bool = False) -> ComparisonRequest:
    q = select(ComparisonRequest).where(ComparisonRequest.id == request_id)
    req = db.execute(q.with_for_update() if lock else q).scalar_one_or_none()
    # Non-parties cannot distinguish someone else's request from a missing one.
    if req is None or me.id not in (req.requester_id, req.recipient_id):
        raise problem(404, "request_not_found", "no such request")
    return req


@router.get("/requests/{request_id}")
def get_request(request_id: str, me: Researcher = Depends(verified_researcher), db: Session = Depends(get_db),
                clock: Clock = Depends(get_clock)) -> dict:
    return view(db, _party_request(db, me, request_id), clock.now())


@router.get("/requests/{request_id}/result")
def get_result(request_id: str, me: Researcher = Depends(verified_researcher), db: Session = Depends(get_db),
               clock: Clock = Depends(get_clock)) -> dict:
    req = _party_request(db, me, request_id)
    ch = db.get(Channel, req.channel_id) if req.channel_id else None
    if me.id == req.recipient_id and req.result_visibility == "requester_only":
        raise problem(403, "result_not_visible", "the result is visible to the requester only")
    status = request_status(req, ch, clock.now())
    # Results are produced in Phase 4; until then nothing (and never anything for non-completed requests).
    raise problem(409, "result_unavailable", f"no result is available for a {status.lower()} request")


# ---- decisions --------------------------------------------------------------------------------

def _decide(action: str, request_id: str, me: Researcher, db: Session, clock: Clock) -> dict:
    peek = _party_request(db, me, request_id)
    ch = None
    if peek.channel_id:  # lock order: channel, then request
        ch = db.execute(select(Channel).where(Channel.id == peek.channel_id).with_for_update()).scalar_one()
    req = _party_request(db, me, request_id, lock=True)
    now = clock.now()
    actor_must_be = req.recipient_id if action in ("approve", "reject") else req.requester_id
    if me.id != actor_must_be:
        record(db, clock, actor_id=me.id, action=f"request.{action}", object_type="request", object_id=req.id,
               decision="deny", reason_code="not_authorized")
        db.commit()
        who = "recipient" if action in ("approve", "reject") else "requester"
        raise problem(403, "not_authorized", f"only the {who} may {action} this request")

    status = request_status(req, ch, now)
    allowed = {"approve": ("PENDING",), "reject": ("PENDING",), "cancel": ("PENDING", "APPROVED")}[action]
    if status not in allowed:
        if status == "EXPIRED" and req.status != "EXPIRED":
            _set_status(db, clock, req, "EXPIRED", "lifetime_elapsed", None, "request.expire",
                        [req.requester_id, req.recipient_id], "request_expired")
        record(db, clock, actor_id=me.id, action=f"request.{action}", object_type="request", object_id=req.id,
               decision="deny", reason_code=f"request_{status.lower()}")
        db.commit()
        raise problem(409, f"request_{status.lower()}", f"cannot {action} a {status.lower()} request")

    if action == "approve":
        if ch is not None:
            ch_status = channel_status(ch, now)
            if ch_status not in ("ACTIVE", "PAUSED"):
                record(db, clock, actor_id=me.id, action="request.approve", object_type="request", object_id=req.id,
                       decision="deny", reason_code=f"channel_{ch_status.lower()}")
                db.commit()
                raise problem(409, f"channel_{ch_status.lower()}", f"channel is {ch_status.lower()}")
            policy, version = channel_policy(ch), ch.policy_version
        else:
            policy, version = targeted_policy(me), None
        why = incompatibility(req.requested_scope, req.result_visibility, policy)
        if why:
            _set_status(db, clock, req, "CANCELLED", "policy_incompatible", me.id, "request.invalidate",
                        [req.requester_id, req.recipient_id], "request_invalidated", version)
            db.commit()
            raise problem(409, "policy_incompatible", f"request no longer fits the current policy ({why})")
        req.approved_policy_version = version
        _set_status(db, clock, req, "APPROVED", None, me.id, "request.approve", [req.requester_id],
                    "request_approved", version)
    elif action == "reject":
        _set_status(db, clock, req, "REJECTED", "recipient_rejected", me.id, "request.reject", [req.requester_id],
                    "request_rejected", ch.policy_version if ch else None)
    else:
        _set_status(db, clock, req, "CANCELLED", "requester_cancelled", me.id, "request.cancel", [req.recipient_id],
                    "request_cancelled", ch.policy_version if ch else None)
    db.commit()
    return view(db, req, now)


def _decision_endpoint(action: str):
    def endpoint(request_id: str, me: Researcher = Depends(verified_researcher), db: Session = Depends(get_db),
                 clock: Clock = Depends(get_clock)) -> dict:
        return _decide(action, request_id, me, db, clock)

    endpoint.__name__ = f"{action}_request"
    return endpoint


for _action in ("approve", "reject", "cancel"):
    router.add_api_route(f"/requests/{{request_id}}/{_action}", _decision_endpoint(_action), methods=["POST"])


def party_request_ids(db: Session, researcher_id: str) -> list[str]:
    return list(db.scalars(select(ComparisonRequest.id).where(
        or_(ComparisonRequest.requester_id == researcher_id, ComparisonRequest.recipient_id == researcher_id))))
