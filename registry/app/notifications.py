"""In-app notifications about requests. Nothing is ever sent outside the app."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .clock import Clock, as_utc
from .deps import current_researcher, get_clock, get_db, problem
from .models import Notification, Researcher

router = APIRouter(prefix="/v1/notifications")


def notify(db: Session, clock: Clock, recipient_id: str, kind: str, request_id: str | None) -> None:
    db.add(Notification(recipient_id=recipient_id, kind=kind, request_id=request_id, created_at=clock.now()))


@router.get("")
def list_notifications(unread_only: bool = False, me: Researcher = Depends(current_researcher),
                       db: Session = Depends(get_db)) -> dict:
    q = select(Notification).where(Notification.recipient_id == me.id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    rows = db.scalars(q.order_by(Notification.created_at.desc(), Notification.id)).all()
    return {"notifications": [{"id": n.id, "kind": n.kind, "request_id": n.request_id,
                               "created_at": as_utc(n.created_at).isoformat(),
                               "read": n.read_at is not None} for n in rows]}


@router.post("/{notification_id}/read")
def mark_read(notification_id: str, me: Researcher = Depends(current_researcher), db: Session = Depends(get_db),
              clock: Clock = Depends(get_clock)) -> dict:
    n = db.get(Notification, notification_id)
    if n is None or n.recipient_id != me.id:
        raise problem(404, "notification_not_found", "no such notification")
    n.read_at = n.read_at or clock.now()
    db.commit()
    return {"id": n.id, "read": True}
