"""Create chat_rooms and chat_messages.

Revision ID: 0035_create_chat_tables
Revises: 0034_dedupe_fcm_tokens
Create Date: 2026-11-17

채팅(docs/design-docs/chat-architecture.md 데이터 모델). 지원(Offer) 1건당 채팅방 1개이고,
채팅방 안의 채팅은 `seq`로 저장 순서를 가진다. 상태값은 VARCHAR + 이름 붙인 CHECK로 고정한다
(CLAUDE.md, app/models/enum_type.py의 check_constraint_name 규약).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0035_create_chat_tables"
down_revision = "0034_dedupe_fcm_tokens"
branch_labels = None
depends_on = None


ROOM_STATUSES = ("ACTIVE", "INACTIVE", "CLOSED")
ROOM_STATUS_REASONS = (
    "ORDERER_DISPUTED",
    "RUNNER_DISPUTED",
    "NOT_SELECTED",
    "OFFER_CANCELLED",
    "PROPOSAL_CANCELLED",
    "ADMIN_CANCELLED",
    "ALL_CONFIRMED",
    "DISPUTE_COMPLETED",
    "DISPUTE_FAILED",
)
MESSAGE_TYPES = ("USER", "SYSTEM")
SYSTEM_EVENTS = (
    "OFFER_CREATED",
    "MATCHED",
    "NOT_SELECTED",
    "OFFER_CANCELLED",
    "RUNNER_COMPLETED",
    "ORDERER_CONFIRMED",
    "ALL_CONFIRMED",
    "DISPUTE_RAISED",
    "DISPUTE_COMPLETED",
    "DISPUTE_FAILED",
    "PROPOSAL_CANCELLED",
    "ADMIN_CANCELLED_AFTER_MATCH",
    "PAYOUT_COMPLETED",
    "REFUND_COMPLETED",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("chat_rooms"):
        op.create_table(
            "chat_rooms",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("offer_id", sa.BigInteger(), nullable=False),
            sa.Column("proposal_id", sa.BigInteger(), nullable=False),
            sa.Column("orderer_id", sa.String(length=36), nullable=False),
            sa.Column("runner_id", sa.String(length=36), nullable=False),
            sa.Column("status", sa.String(length=10), nullable=False),
            sa.Column("status_reason", sa.String(length=30), nullable=True),
            sa.Column("last_seq", sa.BigInteger(), server_default="0", nullable=False),
            sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("orderer_last_read_seq", sa.BigInteger(), server_default="0", nullable=False),
            sa.Column("runner_last_read_seq", sa.BigInteger(), server_default="0", nullable=False),
            sa.Column("version", sa.BigInteger(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("offer_id", name="uk_chat_rooms_offer_id"),
            sa.CheckConstraint(_in("status", ROOM_STATUSES), name="ck_chat_rooms_status_values"),
            sa.CheckConstraint(_in("status_reason", ROOM_STATUS_REASONS), name="ck_chat_rooms_status_reason_values"),
        )
        op.create_index("ix_chat_rooms_proposal_id", "chat_rooms", ["proposal_id"])
        op.create_index("idx_chat_rooms_orderer_last_message", "chat_rooms", ["orderer_id", "last_message_at"])
        op.create_index("idx_chat_rooms_runner_last_message", "chat_rooms", ["runner_id", "last_message_at"])

    if not inspector.has_table("chat_messages"):
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("room_id", sa.BigInteger(), nullable=False),
            sa.Column("seq", sa.BigInteger(), nullable=False),
            sa.Column("type", sa.String(length=10), nullable=False),
            sa.Column("sender_id", sa.String(length=36), nullable=True),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("system_event", sa.String(length=40), nullable=True),
            sa.Column("system_payload", sa.JSON(), nullable=True),
            sa.Column("system_event_key", sa.String(length=100), nullable=True),
            sa.Column("client_message_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("room_id", "seq", name="uk_chat_messages_room_seq"),
            sa.UniqueConstraint("room_id", "system_event_key", name="uk_chat_messages_room_system_event_key"),
            sa.UniqueConstraint("sender_id", "client_message_id", name="uk_chat_messages_sender_client_message_id"),
            sa.CheckConstraint(_in("type", MESSAGE_TYPES), name="ck_chat_messages_type_values"),
            sa.CheckConstraint(_in("system_event", SYSTEM_EVENTS), name="ck_chat_messages_system_event_values"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("chat_messages"):
        op.drop_table("chat_messages")
    if inspector.has_table("chat_rooms"):
        op.drop_table("chat_rooms")
