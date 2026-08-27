"""Proposal report API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.proposal import ProposalStatus
from app.models.proposal_report import ProposalReportStatus


class ProposalReportReasonQuestionResponse(BaseModel):
    id: int
    question_text: str = Field(..., serialization_alias="questionText")
    display_order: int = Field(..., serialization_alias="displayOrder")
    requires_detail: bool = Field(
        ...,
        serialization_alias="requiresDetail",
        description="상세 사유 필수 여부. 기타 문항만 true다.",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ProposalReportCreateRequest(BaseModel):
    """신고 요청. 분쟁·탈퇴와 같이 사유 선택은 필수이고 상세 사유는 기타 사유에서만 필수다."""

    reason_question_id: int = Field(..., validation_alias="reasonQuestionId", ge=1)
    detail_reason: str | None = Field(None, validation_alias="detailReason", max_length=500)

    @field_validator("detail_reason")
    @classmethod
    def validate_detail_reason(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ProposalReportResponse(BaseModel):
    """신고 응답. 분쟁·탈퇴와 같은 사유 3종을 반환한다. 상세 사유만 null일 수 있다."""

    id: int
    proposal_id: int = Field(..., serialization_alias="proposalId")
    reporter_id: str = Field(..., serialization_alias="reporterId")
    reporter_name: str | None = Field(
        None,
        serialization_alias="reporterName",
        description="신고자 이름. 관리자 조회에서만 채워지며 탈퇴한 사용자는 null이다.",
    )
    reason_question_id: int = Field(..., serialization_alias="reasonQuestionId")
    reason_question_text: str = Field(..., serialization_alias="reasonQuestionText")
    detail_reason: str | None = Field(None, serialization_alias="detailReason")
    status: ProposalReportStatus
    created_at: datetime = Field(..., serialization_alias="createdAt")
    reviewed_at: datetime | None = Field(None, serialization_alias="reviewedAt")
    proposal_status: ProposalStatus | None = Field(
        None,
        serialization_alias="proposalStatus",
        description="신고 대상 요청의 현재 상태. 관리자 목록 조회에서만 채워진다.",
    )

    model_config = ConfigDict(populate_by_name=True)
