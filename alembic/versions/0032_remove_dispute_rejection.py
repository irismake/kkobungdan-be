"""Remove the dispute rejection outcome.

Revision ID: 0032_remove_dispute_rejection
Revises: 0031_refund_deposit_review_statuses
Create Date: 2026-08-26

분쟁 반려는 Proposal/Offer/Mission 상태를 바꾸지 않아 반려된 요청이 `DISPUTED`에 영구히
갇혔다. 판정 결과는 꼬붕 책임(`FAILED`)과 행님 책임(`COMPLETED`) 둘뿐이므로 반려를 없앤다.
반려된 기존 건은 아직 결론이 나지 않은 상태이므로 재판정 대기(`PENDING`)로 되돌린다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0032_remove_dispute_rejection"
down_revision = "0031_refund_deposit_review_statuses"
branch_labels = None
depends_on = None


TABLE = "dispute_evidences"
COLUMN = "status"
CONSTRAINT = f"ck_{TABLE}_{COLUMN}_values"
NEW_VALUES = ("PENDING", "RESOLVED")
OLD_VALUES = ("PENDING", "RESOLVED", "REJECTED")


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        return

    # 반려는 결론이 아니라 판단 보류였다. 관리자가 다시 판정할 수 있도록 대기로 되돌린다.
    bind.execute(
        sa.text(
            f"UPDATE {TABLE} SET {COLUMN} = 'PENDING', resolved_at = NULL, "
            "resolved_by_admin_id = NULL WHERE status = 'REJECTED'"
        )
    )
    _replace_constraint(bind, NEW_VALUES)


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        return

    # 되돌린 반려 건은 복구할 수 없다. 허용값만 원래대로 넓힌다.
    _replace_constraint(bind, OLD_VALUES)


def _replace_constraint(bind, allowed: tuple[str, ...]) -> None:
    if _has_constraint(bind, CONSTRAINT):
        op.drop_constraint(CONSTRAINT, TABLE, type_="check")

    op.create_check_constraint(
        CONSTRAINT,
        TABLE,
        sa.text(f"{COLUMN} IN :allowed").bindparams(
            sa.bindparam("allowed", value=allowed, expanding=True, literal_execute=True)
        ),
    )


def _has_constraint(bind, constraint_name: str) -> bool:
    return (
        bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = :table "
                "AND CONSTRAINT_NAME = :name"
            ),
            {"table": TABLE, "name": constraint_name},
        ).scalar_one()
        > 0
    )
