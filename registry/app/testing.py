"""Test-mode-only controls: adjustable clock and demo reset. Not mounted unless FKG_TEST_MODE=1."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session

from .clock import Clock
from .config import Settings
from .deps import get_clock, get_db, get_settings
from .identity import seed_researchers
from .execution import sync_agent_clocks
from .models import (AuditEvent, Channel, ChannelPolicyVersion, ComparisonRequest, ComparisonResult,
                     Notification, Ticket)

router = APIRouter(prefix="/v1/test", tags=["test-mode"])


class Advance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seconds: float = Field(gt=0, le=7 * 24 * 3600)


@router.get("/clock")
def get_clock_state(clock: Clock = Depends(get_clock)) -> dict:
    return {"now": clock.now().isoformat(), "offset_seconds": clock.offset_seconds}


@router.post("/clock/advance")
def advance_clock(body: Advance, request: Request, clock: Clock = Depends(get_clock)) -> dict:
    clock.advance(body.seconds)
    return {"now": clock.now().isoformat(), "offset_seconds": clock.offset_seconds,
            "agents_synced": sync_agent_clocks(request.app)}


class AgentDelay(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seconds: float = Field(ge=0, le=30)


@router.post("/agent-delay")
def set_agent_delay(body: AgentDelay, request: Request) -> dict:
    """Widen the compute-to-release window so revoke-during-compute races are testable."""
    request.app.state.test_agent_delay = body.seconds
    return {"agent_delay_seconds": body.seconds}


@router.post("/reset")
def reset_demo(request: Request, db: Session = Depends(get_db), clock: Clock = Depends(get_clock),
               settings: Settings = Depends(get_settings)) -> dict:
    for model in (Notification, ComparisonResult, Ticket, ComparisonRequest, ChannelPolicyVersion, Channel,
                  AuditEvent):
        db.execute(delete(model))
    db.commit()
    seed_researchers(db, settings)
    clock.reset()
    request.app.state.test_agent_delay = 0.0
    return {"reset": True, "agents_synced": sync_agent_clocks(request.app)}
