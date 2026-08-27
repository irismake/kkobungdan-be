"""Replace every MySQL ENUM column with VARCHAR.

Revision ID: 0029_replace_mysql_enums_with_varchar
Revises: 0028_seed_dispute_survey_questions
Create Date: 2026-08-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision = "0029_replace_mysql_enums_with_varchar"
down_revision = "0028_seed_dispute_survey_questions"
branch_labels = None
depends_on = None


# CLAUDE.md: DB 컬럼에 MySQL native ENUM을 쓰지 않고 VARCHAR를 쓴다. 상태값을 추가할 때
# ALTER TABLE이 필요 없게 하기 위해서다. 모델은 non-native Enum 매핑을 써서 애플리케이션에는
# 여전히 Python Enum을 돌려주므로, 이 마이그레이션은 DDL만 바꾸고 앱 동작은 그대로다.
# 미션·환불·분쟁증빙은 이미 VARCHAR라 남은 6개만 맞춘다.
# (table, column, varchar length, 되돌릴 때 쓸 ENUM 값)
ENUM_COLUMNS: tuple[tuple[str, str, int, tuple[str, ...]], ...] = (
    ("auth_phone_verifications", "purpose", 10, ("SIGNUP", "LOGIN")),
    ("auth_phone_verifications", "status", 20, ("PENDING", "VERIFIED", "EXPIRED")),
    ("dispute_survey_questions", "target_type", 10, ("ORDER", "RUNNER")),
    (
        "offers",
        "status",
        20,
        ("WAITING", "ACCEPTED", "RUNNER_COMPLETED", "ALL_COMPLETED", "DISPUTED", "REJECTED", "CANCELLED"),
    ),
    ("proposal_reports", "status", 20, ("PENDING", "ACCEPTED", "REJECTED")),
    (
        "proposals",
        "status",
        20,
        (
            "HOLDING",
            "POSTED",
            "OFFERED",
            "MATCHED",
            "ORDER_COMPLETED",
            "ALL_COMPLETED",
            "DISPUTED",
            "REFUND_PENDING",
            "REFUNDED",
            "REPORTED",
            "CANCELLED",
        ),
    ),
)


def upgrade() -> None:
    bind = op.get_bind()

    for table_name, column_name, length, enum_values in ENUM_COLUMNS:
        if not _is_enum(bind, table_name, column_name):
            continue
        # MODIFY COLUMN이라 인덱스와 값은 그대로 남는다. ENUM 문자열이 그대로 VARCHAR로 옮겨진다.
        op.alter_column(
            table_name,
            column_name,
            existing_type=mysql.ENUM(*enum_values),
            type_=sa.String(length=length),
            existing_nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()

    for table_name, column_name, length, enum_values in ENUM_COLUMNS:
        if _is_enum(bind, table_name, column_name):
            continue
        # 열거형 밖의 값이 하나라도 있으면 ENUM 전환이 실패한다. strict mode(MySQL 8 기본)에서는
        # ERROR 1265로 죽고, non-strict mode에서는 빈 문자열로 잘린다. 어느 쪽이든 여기서 먼저 막고
        # 원인을 알려준다.
        unexpected = bind.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {table_name} "
                f"WHERE {column_name} NOT IN :allowed"
            ).bindparams(sa.bindparam("allowed", value=enum_values, expanding=True))
        ).scalar_one()
        if unexpected:
            raise RuntimeError(
                f"{table_name}.{column_name}에 ENUM 밖의 값이 {unexpected}건 있어 되돌릴 수 없다. "
                "먼저 값을 정리해야 한다."
            )
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.String(length=length),
            type_=mysql.ENUM(*enum_values),
            existing_nullable=False,
        )


def _is_enum(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return False
    for column in inspector.get_columns(table_name):
        if column["name"] == column_name:
            return isinstance(column["type"], mysql.ENUM)
    return False
