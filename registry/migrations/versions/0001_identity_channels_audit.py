"""Identities, discovery channels, immutable channel policy versions, audit events.

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "researchers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("theme", sa.String(256), nullable=False),
        sa.Column("verified_researcher", sa.Boolean, nullable=False),
        sa.Column("published_topics", sa.JSON, nullable=False),
        sa.Column("topic_vocabulary", sa.String(64), nullable=False),
        sa.Column("inspiration", sa.JSON, nullable=True),
        sa.Column("is_simulated", sa.Boolean, nullable=False),
    )
    op.create_table(
        "channels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(64), sa.ForeignKey("researchers.id"), nullable=False, index=True),
        sa.Column("topics", sa.JSON, nullable=False),
        sa.Column("audience", sa.String(32), nullable=False),
        sa.Column("visibility", sa.String(32), nullable=False),
        sa.Column("approval_mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("policy_version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "channel_policy_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("topics", sa.JSON, nullable=False),
        sa.Column("audience", sa.String(32), nullable=False),
        sa.Column("visibility", sa.String(32), nullable=False),
        sa.Column("approval_mode", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(64), sa.ForeignKey("researchers.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("channel_id", "version"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(64), nullable=True, index=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("object_id", sa.String(64), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.Integer, nullable=True),
        sa.Column("decision", sa.String(8), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    for table in ("audit_events", "channel_policy_versions", "channels", "researchers"):
        op.drop_table(table)
