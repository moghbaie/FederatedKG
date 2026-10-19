"""Comparison requests, notifications, disclosure/result-visibility policy fields.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_DEFAULT_VISIBILITY = '["requester_only", "both"]'


def upgrade() -> None:
    for table in ("channels", "channel_policy_versions"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("max_disclosure", sa.String(16), nullable=False,
                                       server_default="score_only"))
            batch.add_column(sa.Column("allowed_result_visibility", sa.JSON, nullable=False,
                                       server_default=_DEFAULT_VISIBILITY))
        # Defaults only backfill existing rows; the application always writes both fields.
        with op.batch_alter_table(table) as batch:
            batch.alter_column("max_disclosure", server_default=None)
            batch.alter_column("allowed_result_visibility", server_default=None)

    op.create_table(
        "comparison_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=True, index=True),
        sa.Column("target_researcher_id", sa.String(64), sa.ForeignKey("researchers.id"), nullable=True),
        sa.Column("requester_id", sa.String(64), sa.ForeignKey("researchers.id"), nullable=False, index=True),
        sa.Column("recipient_id", sa.String(64), sa.ForeignKey("researchers.id"), nullable=False, index=True),
        sa.Column("requested_scope", sa.JSON, nullable=False),
        sa.Column("scope_fingerprint", sa.String(64), nullable=False),
        sa.Column("result_visibility", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("status_reason", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_policy_version", sa.Integer, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.UniqueConstraint("requester_id", "idempotency_key"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recipient_id", sa.String(64), sa.ForeignKey("researchers.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("comparison_requests")
    for table in ("channel_policy_versions", "channels"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("allowed_result_visibility")
            batch.drop_column("max_disclosure")
