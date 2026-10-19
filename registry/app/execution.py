"""Running an approved comparison: ticket issue, agent dispatch, and guarded result release.

The registry never computes similarity and never sees private sets or exact counts. It issues a
signed single-use ticket, asks each result recipient's agent to run PSI-CA with the peer agent, then
re-checks everything under row locks before storing the producer-signed, disclosure-limited package.
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from fkg_protocol.keys import Keyring, load_private
from fkg_protocol.results import package_violations, verify_package
from fkg_protocol.tickets import TICKET_TTL_SECONDS, issue_ticket
from fkg_protocol.tokens import AuthError, ReplayCache, sign_service_token, verify_service_token, wall_now

from .audit import record
from .clock import Clock, as_utc
from .config import Settings
from .deps import get_clock, get_db, problem, verified_researcher
from .models import Channel, ComparisonRequest, ComparisonResult, Notification, Researcher, Ticket
from .notifications import notify
from .policy import incompatibility
from .requests import _party_request, _set_status, execution_check, view
from .status import channel_policy, channel_status, request_status

router = APIRouter()
SERVICE_ID = "registry"
TOKEN_HEADER = "X-Service-Token"
AGENT_TIMEOUT_SECONDS = 60.0


class ServiceIdentity:
    def __init__(self, settings: Settings):
        self.available = bool(settings.private_key_path and settings.keyring_dir
                              and settings.private_key_path.exists() and settings.keyring_dir.exists())
        self.key = load_private(settings.private_key_path) if self.available else None
        self.keyring = Keyring.from_dir(settings.keyring_dir) if self.available else Keyring({})
        self.replay = ReplayCache()


def install(app: FastAPI, settings: Settings) -> None:
    app.state.identity = ServiceIdentity(settings)
    app.state.agent_transport = None  # tests inject an httpx transport that simulates agents
    app.state.test_agent_delay = 0.0
    if app.state.identity.available and app.state.identity.keyring.get("registry") is None:
        raise RuntimeError("registry public key missing from keyring")
    app.include_router(router)


def _agent_client(app: FastAPI) -> httpx.Client:
    return httpx.Client(transport=app.state.agent_transport, timeout=AGENT_TIMEOUT_SECONDS)


def call_agent(app: FastAPI, persona: str, method: str, path: str, payload: dict | None, now: float,
               headers: dict | None = None) -> httpx.Response:
    base = app.state.settings.agent_urls[persona].rstrip("/")
    body = json.dumps(payload).encode() if payload is not None else b""
    token = sign_service_token(app.state.identity.key, SERVICE_ID, persona, method, path, body, now)
    with _agent_client(app) as client:
        return client.request(method, base + path, content=body,
                              headers={TOKEN_HEADER: token, "Content-Type": "application/json", **(headers or {})})


# ---- run --------------------------------------------------------------------------------------

@router.post("/v1/requests/{request_id}/run", status_code=202)
def run_comparison(request_id: str, request: Request, background: BackgroundTasks,
                   me: Researcher = Depends(verified_researcher), db: Session = Depends(get_db),
                   clock: Clock = Depends(get_clock)) -> dict:
    app = request.app
    if not app.state.identity.available:
        raise problem(503, "service_identity_unavailable", "registry signing keys are not configured")
    peek = _party_request(db, me, request_id)
    ch = None
    if peek.channel_id:
        ch = db.execute(select(Channel).where(Channel.id == peek.channel_id).with_for_update()).scalar_one()
    req = _party_request(db, me, request_id, lock=True)
    if me.id != req.requester_id:
        record(db, clock, actor_id=me.id, action="request.run", object_type="request", object_id=req.id,
               decision="deny", reason_code="not_authorized")
        db.commit()
        raise problem(403, "not_authorized", "only the requester may start the comparison")
    now = clock.now()
    check = execution_check(db, req, now)
    if not check["ok"]:
        record(db, clock, actor_id=me.id, action="request.run", object_type="request", object_id=req.id,
               decision="deny", reason_code=check["reason"])
        db.commit()
        raise problem(409, check["reason"], "the comparison is not authorized to run now")

    recipients = [req.requester_id] + ([req.recipient_id] if req.result_visibility == "both" else [])
    claims = {"jti": uuid.uuid4().hex, "request_id": req.id, "requester_id": req.requester_id,
              "recipient_id": req.recipient_id, "protocol": req.requested_scope["protocol"],
              "scope": req.requested_scope, "scope_fingerprint": req.scope_fingerprint,
              "channel_id": req.channel_id, "policy_version": req.approved_policy_version,
              "result_recipients": recipients}
    token = issue_ticket(app.state.identity.key, claims, now.timestamp())
    db.add(Ticket(id=claims["jti"], request_id=req.id, status="ISSUED", policy_version=req.approved_policy_version,
                  issued_at=now, expires_at=now + timedelta(seconds=TICKET_TTL_SECONDS)))
    _set_status(db, clock, req, "RUNNING", None, me.id, "request.run", [], "", req.approved_policy_version)
    db.commit()
    background.add_task(dispatch, app, req.id, token, claims)
    return view(db, req, now)


def dispatch(app: FastAPI, request_id: str, ticket: str, claims: dict) -> None:
    """Ask each result recipient's agent to compute; collect verified packages; then release."""
    clock: Clock = app.state.clock
    packages: dict[str, tuple[dict, str]] = {}
    failure = None
    delay = {"X-FKG-Test-Delay": str(app.state.test_agent_delay)} if app.state.settings.test_mode else {}
    for consumer in claims["result_recipients"]:
        try:
            r = call_agent(app, consumer, "POST", "/internal/comparisons/run",
                           {"ticket": ticket, "consumer_id": consumer}, clock.now().timestamp(), delay)
        except httpx.HTTPError:
            failure = "agent_unreachable"
            break
        if r.status_code != 200:
            try:
                failure = r.json()["detail"]["code"]
            except Exception:
                failure = f"agent_http_{r.status_code}"
            break
        try:
            signed = r.json()["package"]
            pkg = verify_package(signed, app.state.identity.keyring.get(consumer))
        except (AuthError, KeyError, ValueError, TypeError):
            failure = "package_signature_invalid"
            break
        expected = {"request_id": claims["request_id"], "ticket_id": claims["jti"], "consumer_id": consumer,
                    "producer_id": consumer, "scope": claims["scope"]}
        if any(pkg.get(k) != v for k, v in expected.items()) or package_violations(pkg, claims["scope"]["disclosure"]):
            failure = "package_rejected"
            break
        packages[consumer] = (pkg, signed)
    release(app, request_id, claims["jti"], packages, failure)


def release(app: FastAPI, request_id: str, ticket_id: str, packages: dict, failure: str | None) -> None:
    clock: Clock = app.state.clock
    with app.state.sessionmaker() as db:
        req0 = db.get(ComparisonRequest, request_id)
        ch = None
        if req0.channel_id:
            ch = db.execute(select(Channel).where(Channel.id == req0.channel_id).with_for_update()).scalar_one()
        req = db.execute(select(ComparisonRequest).where(ComparisonRequest.id == request_id)
                         .with_for_update()).scalar_one()
        ticket = db.execute(select(Ticket).where(Ticket.id == ticket_id).with_for_update()).scalar_one()
        now = clock.now()
        parties = [req.requester_id, req.recipient_id]

        def withhold(reason: str) -> None:
            record(db, clock, actor_id=None, action="result.withhold", object_type="request", object_id=req.id,
                   decision="deny", reason_code=reason, policy_version=ticket.policy_version)

        if req.status != "RUNNING" or ticket.status != "ISSUED":
            withhold(f"request_{req.status.lower()}" if req.status != "RUNNING" else f"ticket_{ticket.status.lower()}")
        elif failure:
            _set_status(db, clock, req, "FAILED", failure, None, "request.fail", parties, "request_failed",
                        ticket.policy_version)
            withhold(failure)
        elif now >= as_utc(ticket.expires_at) or request_status(req, ch, now) == "EXPIRED":
            _set_status(db, clock, req, "EXPIRED", "lifetime_elapsed", None, "request.expire", parties,
                        "request_expired", ticket.policy_version)
            withhold("expired_before_release")
        elif ch is not None and channel_status(ch, now) != "ACTIVE":
            # Approval stands; the owner paused (or the channel ended), so nothing is released now.
            if channel_status(ch, now) == "PAUSED":
                _set_status(db, clock, req, "APPROVED", "withheld_channel_paused", None, "request.withhold",
                            parties, "result_withheld", ticket.policy_version)
                _revoke(ticket, "channel_paused")
            else:
                _set_status(db, clock, req, "CANCELLED", f"channel_{channel_status(ch, now).lower()}", None,
                            "request.cancel", parties, "request_cancelled", ticket.policy_version)
            withhold(f"channel_{channel_status(ch, now).lower()}")
        elif ch is not None and incompatibility(req.requested_scope, req.result_visibility, channel_policy(ch)):
            _set_status(db, clock, req, "CANCELLED", "policy_incompatible", None, "request.invalidate", parties,
                        "request_invalidated", ch.policy_version)
            withhold("policy_incompatible")
        else:
            for consumer, (pkg, signed) in packages.items():
                db.add(ComparisonResult(request_id=req.id, ticket_id=ticket.id, producer_id=pkg["producer_id"],
                                        consumer_id=consumer, package=pkg, signature=signed, released_at=now))
                record(db, clock, actor_id=None, action="result.release", object_type="request", object_id=req.id,
                       policy_version=ticket.policy_version, correlation_id=consumer)
            ticket.status = "CONSUMED"
            _set_status(db, clock, req, "COMPLETED", None, None, "request.complete", list(packages),
                        "result_available", ticket.policy_version)
        db.commit()


def _revoke(ticket: Ticket, reason: str) -> None:
    if ticket.status == "ISSUED":
        ticket.status, ticket.status_reason = "REVOKED", reason


# ---- results ------------------------------------------------------------------------------------

@router.get("/v1/requests/{request_id}/result")
def get_result(request_id: str, me: Researcher = Depends(verified_researcher), db: Session = Depends(get_db),
               clock: Clock = Depends(get_clock)) -> dict:
    req = _party_request(db, me, request_id)
    if me.id == req.recipient_id and req.result_visibility == "requester_only":
        raise problem(403, "result_not_visible", "the result is visible to the requester only")
    ch = db.get(Channel, req.channel_id) if req.channel_id else None
    status = request_status(req, ch, clock.now())
    row = db.scalars(select(ComparisonResult).where(ComparisonResult.request_id == req.id,
                                                    ComparisonResult.consumer_id == me.id)).one_or_none()
    if status != "COMPLETED" or row is None:
        raise problem(409, "result_unavailable", f"no result is available for a {status.lower()} request")
    pkg = row.package
    out = {"request_id": req.id, "status": status, "protocol": req.requested_scope["protocol"],
           "method": pkg["method"], "algorithm_version": pkg["algorithm_version"],
           "disclosure": req.requested_scope["disclosure"], "results": pkg["results"],
           "disclosed_to_counterpart": pkg["disclosed_to_counterpart"],
           "input_provenance": pkg["input_provenance"], "producer_id": row.producer_id,
           "policy_version": pkg["policy_version"], "released_at": as_utc(row.released_at).isoformat(),
           "signature": {"algorithm": "Ed25519", "signer": row.producer_id, "verified_at_release": True},
           "caveat": "Bands are a display policy: the computing agent saw the exact count. "
                     "PSI-CA reveals set sizes to the other party. Semi-honest model; unreviewed integration."}
    if req.requested_scope["disclosure"] == "summary":
        requester, recipient = db.get(Researcher, req.requester_id), db.get(Researcher, req.recipient_id)
        out["matched_public_topics"] = sorted(set(req.requested_scope["topics"]) & set(requester.published_topics)
                                              & set(recipient.published_topics))
    return out


# ---- optional, manual contact request --------------------------------------------------------------

@router.post("/v1/requests/{request_id}/contact")
def request_contact(request_id: str, me: Researcher = Depends(verified_researcher), db: Session = Depends(get_db),
                    clock: Clock = Depends(get_clock)) -> dict:
    """An explicit, user-initiated in-app notice to the other party. Never sent automatically or externally."""
    req = _party_request(db, me, request_id)
    if req.status != "COMPLETED":
        raise problem(409, "contact_requires_completed_match", "contact can be requested only after a match")
    other = req.recipient_id if me.id == req.requester_id else req.requester_id
    already = db.scalars(select(Notification).where(Notification.request_id == req.id,
                                                    Notification.recipient_id == other,
                                                    Notification.kind == "contact_requested")).first()
    if already is None:
        notify(db, clock, other, "contact_requested", req.id)
        record(db, clock, actor_id=me.id, action="contact.request", object_type="request", object_id=req.id)
        db.commit()
    return {"request_id": req.id, "contact_requested": True, "delivered": "in-app notification only"}


# ---- internal: ticket status for agents ----------------------------------------------------------

@router.get("/internal/tickets/{ticket_id}")
def ticket_status(ticket_id: str, request: Request, db: Session = Depends(get_db),
                  clock: Clock = Depends(get_clock)) -> dict:
    identity: ServiceIdentity = request.app.state.identity
    try:
        claims = verify_service_token(request.headers.get(TOKEN_HEADER), identity.keyring, SERVICE_ID, "GET",
                                      request.url.path, b"", identity.replay, clock.now().timestamp(),
                                      allowed_issuers=("persona_a", "persona_b", "persona_c", "persona_d"))
    except AuthError as e:
        raise problem(401, e.code, "service authentication failed") from None
    ticket = db.get(Ticket, ticket_id)
    req = db.get(ComparisonRequest, ticket.request_id) if ticket else None
    if ticket is None or claims["iss"] not in (req.requester_id, req.recipient_id):
        raise problem(404, "ticket_not_found", "no such ticket")
    status = ticket.status
    if status == "ISSUED" and clock.now() >= as_utc(ticket.expires_at):
        status = "EXPIRED"
    return {"ticket_id": ticket.id, "status": {"ISSUED": "active"}.get(status, status.lower())}


# ---- test mode: keep agent clocks aligned with the registry test clock -----------------------------

def sync_agent_clocks(app: FastAPI) -> dict:
    """Push the registry clock offset to agents. Signed with wall time so it verifies before syncing."""
    if not app.state.identity.available:
        return {}
    out = {}
    for persona in app.state.settings.agent_urls:
        try:
            r = call_agent(app, persona, "POST", "/internal/test/clock",
                           {"offset_seconds": app.state.clock.offset_seconds}, wall_now())
            out[persona] = r.status_code
        except httpx.HTTPError:
            out[persona] = "unreachable"
    return out

