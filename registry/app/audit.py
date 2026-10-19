from __future__ import annotations

from sqlalchemy.orm import Session

from .clock import Clock
from .models import AuditEvent


def record(db: Session, clock: Clock, *, actor_id: str | None, action: str, object_type: str,
           object_id: str | None, decision: str = "allow", reason_code: str | None = None,
           policy_version: int | None = None, correlation_id: str | None = None) -> None:
    """Add an audit event to the current transaction. Callers commit."""
    db.add(AuditEvent(actor_id=actor_id, action=action, object_type=object_type, object_id=object_id,
                      timestamp=clock.now(), decision=decision, reason_code=reason_code,
                      policy_version=policy_version, correlation_id=correlation_id))
