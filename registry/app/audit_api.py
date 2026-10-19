"""Actor-scoped audit view: your own actions plus events on channels you own and requests you are party to."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .channels import reconcile_expired
from .clock import Clock, as_utc
from .deps import current_researcher, get_clock, get_db
from .models import AuditEvent, Channel, Researcher
from .requests import party_request_ids

router = APIRouter(prefix="/v1/audit")


@router.get("")
def my_audit(limit: int = Query(200, ge=1, le=1000), me: Researcher = Depends(current_researcher),
             db: Session = Depends(get_db), clock: Clock = Depends(get_clock)) -> dict:
    reconcile_expired(db, clock)  # record any lapsed channels/requests so the trail is complete
    objects = list(db.scalars(select(Channel.id).where(Channel.owner_id == me.id))) + party_request_ids(db, me.id)
    q = select(AuditEvent).where(or_(AuditEvent.actor_id == me.id, AuditEvent.object_id.in_(objects)))
    rows = db.scalars(q.order_by(AuditEvent.timestamp.desc(), AuditEvent.id).limit(limit)).all()
    return {"events": [{"id": e.id, "actor_id": e.actor_id, "action": e.action, "object_type": e.object_type,
                        "object_id": e.object_id, "timestamp": as_utc(e.timestamp).isoformat(),
                        "policy_version": e.policy_version, "decision": e.decision,
                        "reason_code": e.reason_code} for e in rows]}
