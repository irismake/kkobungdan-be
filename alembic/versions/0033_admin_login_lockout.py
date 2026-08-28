"""Add admin login failure lockout columns.

Revision ID: 0033_admin_login_lockout
Revises: 0032_remove_dispute_rejection
Create Date: 2026-08-27

관리자 로그인에 시도 제한이 없어 공개 인터넷에서 무제한 브루트포스가 가능했다. 관리자
계정이 하나뿐이라 표적이 명확하다. Redis가 없어 IP 단위 제한은 못 하므로 계정 단위로
연속 실패를 세고 잠근다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0033_admin_login_lockout"
down_revision = "0032_remove_dispute_rejection"
branch_labels = None
depends_on = None


TABLE = "users"

# 베이스라인이 현재 모델 메타데이터로 테이블을 만들기 때문에 새 DB에는 이미 있을 수 있다.
NEW_COLUMNS = [
    sa.Column("admin_login_failed_count", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("admin_locked_until", sa.DateTime(timezone=True), nullable=True),
]


def upgrade() -> None:
    existing = _column_names(op.get_bind(), TABLE)
    for column in NEW_COLUMNS:
        if column.name not in existing:
            op.add_column(TABLE, column.copy())


def downgrade() -> None:
    existing = _column_names(op.get_bind(), TABLE)
    for column in reversed(NEW_COLUMNS):
        if column.name in existing:
            op.drop_column(TABLE, column.name)


def _column_names(bind: sa.engine.Connection, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}
