"""Guard every enum-backed VARCHAR column with a named CHECK constraint.

Revision ID: 0030_enum_check_constraints
Revises: 0029_replace_mysql_enums_with_varchar
Create Date: 2026-08-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0030_enum_check_constraints"
down_revision = "0029_replace_mysql_enums_with_varchar"
branch_labels = None
depends_on = None


# CLAUDE.md: native ENUM 대신 VARCHAR + 이름 붙인 CHECK로 허용값을 고정한다.
# 이름 규약은 app/models/enum_type.py의 check_constraint_name()과 같아야 한다.
# 값 목록은 이 시점의 정본을 그대로 굳힌다. 상태값이 바뀌면 새 마이그레이션에서 제약을 갱신한다.
CHECKED_COLUMNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("auth_phone_verifications", "purpose", ("SIGNUP", "LOGIN")),
    ("auth_phone_verifications", "status", ("PENDING", "VERIFIED", "EXPIRED")),
    ("dispute_evidences", "status", ("PENDING", "RESOLVED", "REJECTED")),
    ("dispute_survey_questions", "target_type", ("ORDER", "RUNNER")),
    ("missions", "resolution", ("COMPLETED", "FAILED")),
    ("missions", "status", ("STARTED", "DISPUTED", "COMPLETED", "PAID", "FAILED")),
    (
        "offers",
        "status",
        ("WAITING", "ACCEPTED", "RUNNER_COMPLETED", "ALL_COMPLETED", "DISPUTED", "REJECTED", "CANCELLED"),
    ),
    ("proposal_reports", "status", ("PENDING", "ACCEPTED", "REJECTED")),
    (
        "proposals",
        "status",
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
    ("refunds", "reason", ("USER_CANCELLED", "ADMIN_CANCELLED", "DISPUTE_FAILED")),
    ("refunds", "status", ("PENDING", "COMPLETED")),
)


def upgrade() -> None:
    bind = op.get_bind()

    for table_name, column_name, allowed in CHECKED_COLUMNS:
        constraint_name = f"ck_{table_name}_{column_name}_values"
        if not sa.inspect(bind).has_table(table_name):
            continue
        if _has_constraint(bind, table_name, constraint_name):
            continue

        # 목록 밖의 값이 남아 있으면 제약 추가가 실패한다. 어떤 값이 걸리는지 먼저 알려준다.
        offenders = _offending_values(bind, table_name, column_name, allowed)
        if offenders:
            raise RuntimeError(
                f"{table_name}.{column_name}에 허용 목록 밖의 값이 있어 CHECK 제약을 걸 수 없다: "
                f"{offenders}. 값을 먼저 정리해야 한다."
            )

        op.create_check_constraint(
            constraint_name,
            table_name,
            sa.text(f"{column_name} IN :allowed").bindparams(
                sa.bindparam("allowed", value=allowed, expanding=True, literal_execute=True)
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()

    for table_name, column_name, _ in CHECKED_COLUMNS:
        constraint_name = f"ck_{table_name}_{column_name}_values"
        if _has_constraint(bind, table_name, constraint_name):
            op.drop_constraint(constraint_name, table_name, type_="check")


def _has_constraint(bind, table_name: str, constraint_name: str) -> bool:
    return (
        bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = :table "
                "AND CONSTRAINT_NAME = :name"
            ),
            {"table": table_name, "name": constraint_name},
        ).scalar_one()
        > 0
    )


def _offending_values(bind, table_name: str, column_name: str, allowed: tuple[str, ...]) -> list[str]:
    rows = bind.execute(
        sa.text(
            f"SELECT DISTINCT {column_name} FROM {table_name} "
            f"WHERE {column_name} IS NOT NULL AND {column_name} NOT IN :allowed"
        ).bindparams(sa.bindparam("allowed", value=allowed, expanding=True))
    ).all()
    return [row[0] for row in rows]
