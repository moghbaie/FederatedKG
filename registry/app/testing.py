"""Test-mode-only controls: adjustable clock and demo reset. Not mounted unless FKG_TEST_MODE=1."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session

from .clock import Clock
from .config import Settings
from .deps import get_clock, get_db, get_settings
from .identity import seed_researchers
from .models import AuditEvent, Channel, ChannelPolicyVersion, ComparisonRequest, Notification

router = APIRouter(prefix="/v1/test", tags=["test-mode"])


class Advance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seconds: float = Field(gt=0, le=7 * 24 * 3600)


@router.get("/clock")
def get_clock_state(clock: Clock = Depends(get_clock)) -> dict:
    return {"now": clock.now().isoformat(), "offset_seconds": clock.offset_seconds}


@router.post("/clock/advance")
def advance_clock(body: Advance, clock: Clock = Depends(get_clock)) -> dict:
    clock.advance(body.seconds)
    return {"now": clock.now().isoformat(), "offset_seconds": clock.offset_seconds}


@router.post("/reset")
def reset_demo(db: Session = Depends(get_db), clock: Clock = Depends(get_clock),
               settings: Settings = Depends(get_settings)) -> dict:
    for model in (Notification, ComparisonRequest, ChannelPolicyVersion, Channel, AuditEvent):
        db.execute(delete(model))
    db.commit()
    seed_researchers(db, settings)
    clock.reset()
    return {"reset": True}
