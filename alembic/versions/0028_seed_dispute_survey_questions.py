"""Seed dispute survey questions so every environment gets them from code.

Revision ID: 0028_seed_dispute_survey_questions
Revises: 0027_reason_detail_policy
Create Date: 2026-08-26
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op


revision = "0028_seed_dispute_survey_questions"
down_revision = "0027_reason_detail_policy"
branch_labels = None
depends_on = None


TABLE_NAME = "dispute_survey_questions"

# 신고(0015)·탈퇴(0018)와 같이 사유 마스터를 코드로 넣는다. 문구는 staging 실데이터가 정본이다.
# `기타`만 requires_detail이 True다. 상세 사유 필수 여부의 정본은 이 컬럼이다(0027 참고).
REASONS: dict[str, tuple[tuple[str, bool], ...]] = {
    "ORDER": (
        ("임무를 진행하기 어려워졌어요", False),
        ("꼬봉과 연락이 되지 않아요", False),
        ("임무 수행이 어렵다고 전달받았어요", False),
        ("직접 해결하게 되었어요", False),
        ("기타", True),
    ),
    "RUNNER": (
        ("행님과 연락이 되지 않아요", False),
        ("요청한 임무를 수행하기 어려워요", False),
        ("임무 내용이 변경되었어요", False),
        ("현장 상황으로 진행이 어려워요", False),
        ("기타", True),
    ),
}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE_NAME):
        return

    now = datetime.now(timezone.utc)

    for target_type, reasons in REASONS.items():
        if _row_count(bind, target_type) == 0:
            # 신규 환경만 삽입한다. uk_dispute_survey_questions_target_order가 UNIQUE라
            # 문항이 이미 있는 환경에 무조건 삽입하면 마이그레이션이 깨진다.
            op.bulk_insert(
                sa.table(
                    TABLE_NAME,
                    sa.column("target_type", sa.String()),
                    sa.column("question_text", sa.String()),
                    sa.column("display_order", sa.Integer()),
                    sa.column("is_active", sa.Boolean()),
                    sa.column("requires_detail", sa.Boolean()),
                    sa.column("created_at", sa.DateTime()),
                    sa.column("updated_at", sa.DateTime()),
                ),
                [
                    {
                        "target_type": target_type,
                        "question_text": question_text,
                        "display_order": index,
                        "is_active": True,
                        "requires_detail": requires_detail,
                        "created_at": now,
                        "updated_at": now,
                    }
                    for index, (question_text, requires_detail) in enumerate(reasons, start=1)
                ],
            )
            continue

        # 기존 환경은 문구를 건드리지 않고 requires_detail만 정본에 맞춘다.
        # 문구가 정본과 완전히 일치하는 행만 대상이다. 부분 일치로 `기타`를 추측하지 않는다.
        for question_text, requires_detail in reasons:
            bind.execute(
                sa.text(
                    f"UPDATE {TABLE_NAME} SET requires_detail = :requires_detail "
                    "WHERE target_type = :target_type AND question_text = :question_text "
                    "AND requires_detail <> :requires_detail"
                ),
                {
                    "requires_detail": requires_detail,
                    "target_type": target_type,
                    "question_text": question_text,
                },
            )


def downgrade() -> None:
    """행을 지우지 않는다.

    dispute_evidences.survey_question_id가 이 행들을 참조하므로 삭제하면 기존 분쟁 기록이
    가리킬 문항을 잃는다. 재적용해도 upgrade가 행 수를 보고 삽입을 건너뛰므로 왕복은 안전하다.
    """


def _row_count(bind, target_type: str) -> int:
    return bind.execute(
        sa.text(f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE target_type = :target_type"),
        {"target_type": target_type},
    ).scalar_one()
