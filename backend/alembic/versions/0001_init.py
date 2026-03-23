from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=256), nullable=False),
        sa.Column("canonical_title", sa.String(length=256), nullable=False),
        sa.Column("canonical_message", sa.String(length=2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("station_hints", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("route_hints", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint", name="uq_incidents_fingerprint"),
    )
    op.create_index(op.f("ix_incidents_fingerprint"), "incidents", ["fingerprint"], unique=False)

    op.create_table(
        "raw_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_name", "external_id", name="uq_raw_reports_source_external"),
    )
    op.create_index(op.f("ix_raw_reports_source_name"), "raw_reports", ["source_name"], unique=False)
    op.create_index(op.f("ix_raw_reports_fetched_at"), "raw_reports", ["fetched_at"], unique=False)
    op.create_index(op.f("ix_raw_reports_incident_id"), "raw_reports", ["incident_id"], unique=False)
    op.create_index(
        op.f("ix_raw_reports_source_external"), "raw_reports", ["source_name", "external_id"], unique=False
    )

    op.create_table(
        "subscribers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=False),
        sa.Column("route_preferences", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone_number"),
    )
    op.create_index(op.f("ix_subscribers_phone_number"), "subscribers", ["phone_number"], unique=False)

    op.create_table(
        "classifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("message", sa.String(length=2048), nullable=False),
        sa.Column("evidence_sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("raw_output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_id"),
    )
    op.create_index(op.f("ix_classifications_severity"), "classifications", ["severity"], unique=False)

    op.create_table(
        "send_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("message", sa.String(length=2048), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_id", "subscriber_id", name="uq_send_log_incident_subscriber"),
    )
    op.create_index(op.f("ix_send_log_incident_id"), "send_log", ["incident_id"], unique=False)
    op.create_index(op.f("ix_send_log_subscriber_id"), "send_log", ["subscriber_id"], unique=False)
    op.create_index(op.f("ix_send_log_sent_at"), "send_log", ["sent_at"], unique=False)


def downgrade() -> None:
    op.drop_table("send_log")
    op.drop_table("classifications")
    op.drop_table("raw_reports")
    op.drop_table("subscribers")
    op.drop_table("incidents")

