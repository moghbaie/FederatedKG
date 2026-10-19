from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Researcher(Base):
    """Public discovery profile of a simulated account. Never holds private graph data."""

    __tablename__ = "researchers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128))
    theme: Mapped[str] = mapped_column(String(256))
    verified_researcher: Mapped[bool] = mapped_column(Boolean)
    published_topics: Mapped[list[str]] = mapped_column(JSON)
    topic_vocabulary: Mapped[str] = mapped_column(String(64))
    inspiration: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("researchers.id"), index=True)
    topics: Mapped[list[str]] = mapped_column(JSON)
    audience: Mapped[str] = mapped_column(String(32), default="verified_researchers")
    visibility: Mapped[str] = mapped_column(String(32), default="topics")
    approval_mode: Mapped[str] = mapped_column(String(32), default="manual")
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    policy_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChannelPolicyVersion(Base):
    """Immutable snapshot of a channel's disclosure settings; a new row per change."""

    __tablename__ = "channel_policy_versions"
    __table_args__ = (UniqueConstraint("channel_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    topics: Mapped[list[str]] = mapped_column(JSON)
    audience: Mapped[str] = mapped_column(String(32))
    visibility: Mapped[str] = mapped_column(String(32))
    approval_mode: Mapped[str] = mapped_column(String(32))
    created_by: Mapped[str] = mapped_column(ForeignKey("researchers.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    """Metadata-only audit trail. Must never contain graph payloads, tokens or secrets."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    policy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision: Mapped[str] = mapped_column(String(8))  # allow | deny
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
