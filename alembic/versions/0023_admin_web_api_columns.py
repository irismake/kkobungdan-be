"""Add columns backing the admin web console APIs.

Revision ID: 0023_admin_web_api_columns
Revises: 0022_create_missions
Create Date: 2026-08-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0023_admin_web_api_columns"
down_revision = "0022_create_missions"
branch_labels = None
depends_on = None


# 베이스라인이 현재 모델 메타데이터로 테이블을 만들기 때문에, 새 DB에는 컬럼이 이미 있을 수 있다.
# 기존 마이그레이션과 같이 존재 여부를 확인한 뒤에만 손댄다.
NEW_COLUMNS: dict[str, list[sa.Column]] = {
    # 입금 확인 시점에는 수락된 지원이 없어 오픈채팅방 URL을 지원에 둘 수 없다.
    "proposals": [
        sa.Column("open_chat_url", sa.String(length=500), nullable=True),
        sa.Column("admin_note", sa.String(length=500), nullable=True),
    ],
    "dispute_evidences": [
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("admin_note", sa.String(length=500), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_admin_id", sa.String(length=36), nullable=True),
    ],
    # 지급·환불 반려는 기록만 남기고 미션 상태를 되돌리지 않는다.
    "missions": [
        sa.Column("settlement_rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settlement_rejected_by_admin_id", sa.String(length=36), nullable=True),
        sa.Column("refund_rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refund_rejected_by_admin_id", sa.String(length=36), nullable=True),
    ],
}

DISPUTE_STATUS_INDEX = "idx_dispute_evidences_status"


def upgrade() -> None:
    bind = op.get_bind()
    for table_name, columns in NEW_COLUMNS.items():
        existing = _column_names(bind, table_name)
        for column in columns:
            if column.name in existing:
                continue
            op.add_column(table_name, column.copy())

    if DISPUTE_STATUS_INDEX not in _index_names(bind, "dispute_evidences"):
        op.create_index(DISPUTE_STATUS_INDEX, "dispute_evidences", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    if DISPUTE_STATUS_INDEX in _index_names(bind, "dispute_evidences"):
        op.drop_index(DISPUTE_STATUS_INDEX, table_name="dispute_evidences")

    for table_name, columns in NEW_COLUMNS.items():
        existing = _column_names(bind, table_name)
        for column in reversed(columns):
            if column.name not in existing:
                continue
            op.drop_column(table_name, column.name)


def _column_names(bind: sa.engine.Connection, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(bind: sa.engine.Connection, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name)}
