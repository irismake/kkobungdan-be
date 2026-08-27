"""Dispute evidence API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DisputeRequest(BaseModel):
    """Dispute request. 신고·탈퇴와 같은 사유 필드명과 입력 정책을 쓴다.

    사유 선택은 필수이고, 상세 사유는 그 사유의 `requiresDetail`이 true(기타)일 때만 필수다.
    """

    reason_question_id: int = Field(..., validation_alias="reasonQuestionId", ge=1)
    detail_reason: str | None = Field(None, validation_alias="detailReason")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @field_validator("detail_reason")
    @classmethod
    def strip_detail_reason(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("detailReason must not be blank")
        return stripped


class DisputeEvidenceResponse(BaseModel):
    """Dispute evidence API response.

    신고·탈퇴 응답과 동일하게 사유 3종(reasonQuestionId/reasonQuestionText/detailReason)으로 응답한다.
    사유는 필수 입력이고 상세 사유는 기타 사유에서만 필수라 detailReason만 null일 수 있다.
    """

    id: int
    proposal_id: int = Field(..., serialization_alias="proposalId")
    offer_id: int = Field(..., serialization_alias="offerId")
    actor_id: str = Field(..., serialization_alias="actorId")
    reason_question_id: int = Field(..., serialization_alias="reasonQuestionId")
    reason_question_text: str = Field(..., serialization_alias="reasonQuestionText")
    detail_reason: str | None = Field(None, serialization_alias="detailReason")
    created_at: datetime = Field(..., serialization_alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
