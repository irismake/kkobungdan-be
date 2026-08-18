"""Fix withdrawal reason spelling: 꼬봉 → 꼬붕.

Revision ID: 0020_fix_withdrawal_reason_spelling
Revises: 0019_default_user_alarm_enabled_true
Create Date: 2026-08-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0020_fix_withdrawal_reason_spelling"
down_revision = "0019_default_user_alarm_enabled_true"
branch_labels = None
depends_on = None


OLD_TEXT = "원하는 꼬봉(또는 행님)을 만나기 어려웠어요."
NEW_TEXT = "원하는 꼬붕(또는 행님)을 만나기 어려웠어요."


def _rename(from_text: str, to_text: str) -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("user_withdrawal_reason_questions"):
        return

    bind.execute(
        sa.text(
            "UPDATE user_withdrawal_reason_questions "
            "SET question_text = :to_text "
            "WHERE question_text = :from_text"
        ),
        {"to_text": to_text, "from_text": from_text},
    )


def upgrade() -> None:
    _rename(OLD_TEXT, NEW_TEXT)


def downgrade() -> None:
    _rename(NEW_TEXT, OLD_TEXT)
