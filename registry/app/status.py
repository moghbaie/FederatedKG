"""Effective (clock-derived) statuses. Authorization always uses these, never the stored flag alone."""
from __future__ import annotations

from datetime import datetime

from .clock import as_utc
from .models import Channel, ComparisonRequest, Researcher
from .policy import RESULT_VISIBILITY, Policy

LIVE_CHANNEL = ("ACTIVE", "PAUSED")
OPEN_REQUEST = ("PENDING", "APPROVED", "RUNNING")


def channel_status(ch: Channel, now: datetime) -> str:
    if ch.status in LIVE_CHANNEL and ch.expires_at is not None and now >= as_utc(ch.expires_at):
        return "EXPIRED"
    return ch.status


def request_status(req: ComparisonRequest, channel: Channel | None, now: datetime) -> str:
    if req.status in OPEN_REQUEST:
        if now >= as_utc(req.expires_at):
            return "EXPIRED"
        if channel is not None and channel_status(channel, now) == "EXPIRED":
            return "EXPIRED"
    return req.status


def channel_policy(ch: Channel) -> Policy:
    return Policy(topics=ch.topics, max_disclosure=ch.max_disclosure,
                  allowed_result_visibility=ch.allowed_result_visibility)


def targeted_policy(recipient: Researcher) -> Policy:
    """v1 default for one-to-one requests: any published topic, at most `summary`."""
    return Policy(topics=recipient.published_topics, max_disclosure="summary",
                  allowed_result_visibility=list(RESULT_VISIBILITY))
