"""Comparison tickets and released result packages.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(36), sa.ForeignKey("comparison_requests.id"), nullable=False, index=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("status_reason", sa.String(64), nullable=True),
        sa.Column("policy_version", sa.Integer, nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "comparison_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(36), sa.ForeignKey("comparison_requests.id"), nullable=False, index=True),
        sa.Column("ticket_id", sa.String(64), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("producer_id", sa.String(64), nullable=False),
        sa.Column("consumer_id", sa.String(64), sa.ForeignKey("researchers.id"), nullable=False),
        sa.Column("package", sa.JSON, nullable=False),
        sa.Column("signature", sa.String(4096), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", "consumer_id"),
    )


def downgrade() -> None:
    op.drop_table("comparison_results")
    op.drop_table("tickets")
