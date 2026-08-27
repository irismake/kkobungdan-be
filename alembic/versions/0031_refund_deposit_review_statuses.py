"""Allow REVIEW/VOIDED refund statuses and the PAYMENT_EXPIRED reason.

Revision ID: 0031_refund_deposit_review_statuses
Revises: 0030_enum_check_constraints
Create Date: 2026-08-26

입금 확인 전 취소된 요청도 관리자 입금 대조 대기 환불을 남기도록 허용값을 넓힌다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0031_refund_deposit_review_statuses"
down_revision = "0030_enum_check_constraints"
branch_labels = None
depends_on = None


# (테이블, 컬럼, 새 허용값, 되돌릴 허용값)
CHANGED_COLUMNS: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "refunds",
        "reason",
        ("USER_CANCELLED", "ADMIN_CANCELLED", "DISPUTE_FAILED", "PAYMENT_EXPIRED"),
        ("USER_CANCELLED", "ADMIN_CANCELLED", "DISPUTE_FAILED"),
    ),
    (
        "refunds",
        "status",
        ("REVIEW", "PENDING", "COMPLETED", "VOIDED"),
        ("PENDING", "COMPLETED"),
    ),
)


def upgrade() -> None:
    _apply(new=True)


def downgrade() -> None:
    _apply(new=False)


def _apply(new: bool) -> None:
    bind = op.get_bind()

    for table_name, column_name, added, original in CHANGED_COLUMNS:
        if not sa.inspect(bind).has_table(table_name):
            continue

        allowed = added if new else original
        constraint_name = f"ck_{table_name}_{column_name}_values"

        # 되돌릴 때 새 값이 남아 있으면 제약을 걸 수 없다. 어떤 값이 걸리는지 먼저 알려준다.
        offenders = _offending_values(bind, table_name, column_name, allowed)
        if offenders:
            raise RuntimeError(
                f"{table_name}.{column_name}에 허용 목록 밖의 값이 있어 CHECK 제약을 걸 수 없다: "
                f"{offenders}. 값을 먼저 정리해야 한다."
            )

        if _has_constraint(bind, table_name, constraint_name):
            op.drop_constraint(constraint_name, table_name, type_="check")

        op.create_check_constraint(
            constraint_name,
            table_name,
            sa.text(f"{column_name} IN :allowed").bindparams(
                sa.bindparam("allowed", value=allowed, expanding=True, literal_execute=True)
            ),
        )


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
