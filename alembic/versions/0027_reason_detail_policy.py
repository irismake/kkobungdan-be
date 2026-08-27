"""Require a reason choice everywhere and demand detail only for 기타.

Revision ID: 0027_reason_detail_policy
Revises: 0026_create_refunds
Create Date: 2026-08-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0027_reason_detail_policy"
down_revision = "0026_create_refunds"
branch_labels = None
depends_on = None


ETC_QUESTION_TEXT = "기타"

# 탈퇴와 같은 정책을 쓰기 위해 사유 마스터에 상세 필수 여부를 둔다.
REQUIRES_DETAIL_TABLES = ("dispute_survey_questions", "proposal_report_reason_questions")


def upgrade() -> None:
    bind = op.get_bind()

    for table_name in REQUIRES_DETAIL_TABLES:
        if "requires_detail" in _column_names(bind, table_name):
            continue
        op.add_column(
            table_name,
            sa.Column("requires_detail", sa.Boolean(), nullable=False, server_default="0"),
        )
        bind.execute(
            sa.text(f"UPDATE {table_name} SET requires_detail = 1 WHERE question_text = :text"),
            {"text": ETC_QUESTION_TEXT},
        )

    # 상세 사유는 기타 사유에서만 필수라 컬럼 자체는 nullable이어야 한다.
    _make_nullable(bind, "dispute_evidences", "reason", sa.Text())


def downgrade() -> None:
    bind = op.get_bind()

    # 상세 사유가 비어 있는 행이 남아 있으면 NOT NULL로 되돌릴 수 없다.
    bind.execute(sa.text("DELETE FROM dispute_evidences WHERE reason IS NULL"))

    _make_not_nullable(bind, "dispute_evidences", "reason", sa.Text())

    for table_name in REQUIRES_DETAIL_TABLES:
        if "requires_detail" in _column_names(bind, table_name):
            op.drop_column(table_name, "requires_detail")


def _column_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _column(bind, table_name: str, column_name: str) -> dict | None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return None
    for column in inspector.get_columns(table_name):
        if column["name"] == column_name:
            return column
    return None


def _make_nullable(bind, table_name: str, column_name: str, column_type: sa.types.TypeEngine) -> None:
    column = _column(bind, table_name, column_name)
    if column is None or column["nullable"]:
        return
    op.alter_column(table_name, column_name, existing_type=column_type, nullable=True)


def _make_not_nullable(bind, table_name: str, column_name: str, column_type: sa.types.TypeEngine) -> None:
    column = _column(bind, table_name, column_name)
    if column is None or not column["nullable"]:
        return
    op.alter_column(table_name, column_name, existing_type=column_type, nullable=False)
