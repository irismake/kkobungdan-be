"""Add admin account columns to users.

Revision ID: 0024_add_user_admin_columns
Revises: 0023_admin_web_api_columns
Create Date: 2026-08-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0024_add_user_admin_columns"
down_revision = "0023_admin_web_api_columns"
branch_labels = None
depends_on = None


# 베이스라인이 현재 모델 메타데이터로 테이블을 만들기 때문에 새 DB에는 이미 있을 수 있다.
NEW_COLUMNS = [
    sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="0"),
    sa.Column("admin_username", sa.String(length=50), nullable=True),
]
ADMIN_USERNAME_CONSTRAINT = "uk_users_admin_username"


def upgrade() -> None:
    bind = op.get_bind()
    existing = _column_names(bind, "users")
    for column in NEW_COLUMNS:
        if column.name not in existing:
            op.add_column("users", column.copy())

    # 비밀번호는 마이그레이션에 담지 않는다. 관리자 계정은 기동 시 환경변수로 만든다.
    if ADMIN_USERNAME_CONSTRAINT not in _unique_constraint_names(bind, "users"):
        op.create_unique_constraint(ADMIN_USERNAME_CONSTRAINT, "users", ["admin_username"])


def downgrade() -> None:
    bind = op.get_bind()
    if ADMIN_USERNAME_CONSTRAINT in _unique_constraint_names(bind, "users"):
        op.drop_constraint(ADMIN_USERNAME_CONSTRAINT, "users", type_="unique")

    existing = _column_names(bind, "users")
    for column in reversed(NEW_COLUMNS):
        if column.name in existing:
            op.drop_column("users", column.name)


def _column_names(bind: sa.engine.Connection, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _unique_constraint_names(bind: sa.engine.Connection, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    names = {constraint["name"] for constraint in inspector.get_unique_constraints(table_name)}
    # MySQL은 UNIQUE를 인덱스로도 보고한다.
    names |= {index["name"] for index in inspector.get_indexes(table_name) if index.get("unique")}
    return names
