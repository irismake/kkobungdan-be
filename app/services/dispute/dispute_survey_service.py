"""Dispute survey question query service."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import AppError, api_error
from app.models.dispute_survey import DisputeSurveyQuestion, DisputeSurveyTargetType
from app.schemas.dispute_survey import DisputeSurveyQuestionResponse


class DisputeSurveyService:
    """Read-only service for dispute survey question master data."""

    @staticmethod
    def list_questions(db: Session, target_type: DisputeSurveyTargetType) -> list[DisputeSurveyQuestionResponse]:
        questions = (
            db.query(DisputeSurveyQuestion)
            .filter(
                DisputeSurveyQuestion.target_type == target_type,
                DisputeSurveyQuestion.is_active.is_(True),
            )
            .order_by(DisputeSurveyQuestion.display_order.asc(), DisputeSurveyQuestion.id.asc())
            .all()
        )
        return [DisputeSurveyQuestionResponse.model_validate(question) for question in questions]

    @staticmethod
    def ensure_active_question(
        db: Session,
        question_id: int,
        target_type: DisputeSurveyTargetType,
    ) -> DisputeSurveyQuestion:
        question = (
            db.query(DisputeSurveyQuestion)
            .filter(
                DisputeSurveyQuestion.id == question_id,
                DisputeSurveyQuestion.target_type == target_type,
                DisputeSurveyQuestion.is_active.is_(True),
            )
            .one_or_none()
        )
        if question is None:
            raise api_error(AppError.VALIDATION_ERROR, "reasonQuestionId")
        return question

    @staticmethod
    def resolve_reason(
        db: Session,
        question_id: int,
        detail_reason: str | None,
        target_type: DisputeSurveyTargetType,
    ) -> DisputeSurveyQuestion:
        """분쟁 사유를 검증한다. 사유는 필수이고 기타 사유만 상세 사유를 요구한다. 탈퇴·신고와 같은 정책이다."""
        question = DisputeSurveyService.ensure_active_question(db, question_id, target_type)
        if question.requires_detail and detail_reason is None:
            raise api_error(AppError.VALIDATION_ERROR, "detailReason")
        return question
