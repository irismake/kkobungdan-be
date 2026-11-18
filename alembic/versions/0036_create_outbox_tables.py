"""Create outbox_events and event_deliveries (공통 Transactional Outbox).

Revision ID: 0036_create_outbox_tables
Revises: 0035_create_chat_tables
Create Date: 2026-11-17

docs/design-docs/outbox.md 데이터 모델. 이벤트 1건은 outbox_events 1행, 전달 대상별 처리는
event_deliveries 1행이다. (event_id, consumer) 유니크가 중복 처리 방지 키다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0036_create_outbox_tables"
down_revision = "0035_create_chat_tables"
branch_labels = None
depends_on = None


DELIVERY_STATUSES = ("PENDING", "PROCESSING", "SUCCEEDED", "FAILED", "SKIPPED", "DEAD")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("outbox_events"):
        op.create_table(
            "outbox_events",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("event_id", sa.String(length=36), nullable=False),
            sa.Column("event_type", sa.String(length=60), nullable=False),
            sa.Column("aggregate_type", sa.String(length=30), nullable=False),
            sa.Column("aggregate_id", sa.String(length=64), nullable=False),
            sa.Column("schema_version", sa.SmallInteger(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("publish_attempts", sa.Integer(), server_default="0", nullable=False),
            sa.Column("next_publish_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_publish_error", sa.String(length=500), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("event_id", name="uk_outbox_events_event_id"),
        )
        op.create_index("idx_outbox_events_unpublished", "outbox_events", ["published_at", "next_publish_at", "id"])
        op.create_index("idx_outbox_events_aggregate", "outbox_events", ["aggregate_type", "aggregate_id", "id"])

    if not inspector.has_table("event_deliveries"):
        statuses = ", ".join(repr(status) for status in DELIVERY_STATUSES)
        op.create_table(
            "event_deliveries",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("event_id", sa.String(length=36), nullable=False),
            sa.Column("consumer", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=12), nullable=False),
            sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.String(length=500), nullable=True),
            sa.Column("skip_reason", sa.String(length=50), nullable=True),
            sa.Column("dead_alerted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("manual_retry_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("last_manual_retry_by", sa.String(length=36), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("event_id", "consumer", name="uk_event_deliveries_event_consumer"),
            sa.CheckConstraint(f"status IN ({statuses})", name="ck_event_deliveries_status_values"),
        )
        op.create_index("idx_event_deliveries_status_next_attempt", "event_deliveries", ["status", "next_attempt_at"])
        op.create_index("idx_event_deliveries_status_locked", "event_deliveries", ["status", "locked_until"])
        op.create_index(
            "idx_event_deliveries_consumer_status_finished", "event_deliveries", ["consumer", "status", "finished_at"]
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("event_deliveries"):
        op.drop_table("event_deliveries")
    if inspector.has_table("outbox_events"):
        op.drop_table("outbox_events")
