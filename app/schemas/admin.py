"""Admin console request and response schemas. 관리자 웹 전용이며 앱에는 노출하지 않는다."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.dispute_evidence import DisputeProcessStatus
from app.models.mission import MissionResolution, PayoutStatus
from app.models.offer import OfferStatus
from app.models.proposal import ProposalStatus
from app.models.proposal_report import ProposalReportStatus
from app.models.refund import RefundReason, RefundStatus


#: 분쟁 당사자의 역할.
ORDERER_ROLE = "ORDERER"
RUNNER_ROLE = "RUNNER"


class AdminLoginRequest(BaseModel):
    """관리자 로그인 요청."""

    username: str = Field(..., min_length=1, max_length=50, description="관리자 아이디")
    password: str = Field(..., min_length=1, max_length=200, description="관리자 비밀번호")

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={"example": {"username": "admin", "password": "password"}},
    )

    @field_validator("username", "password")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class AdminConfirmPaymentRequest(BaseModel):
    """입금 확인 요청. 오픈채팅방 URL을 함께 저장한다."""

    open_chat_url: str = Field(
        ...,
        max_length=500,
        validation_alias="openChatUrl",
        description="오픈채팅방 URL. http:// 또는 https:// 로 시작해야 한다.",
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @field_validator("open_chat_url")
    @classmethod
    def _validate_scheme(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("openChatUrl must start with http:// or https://")
        return value


class AdminProposalResponse(BaseModel):
    """관리자 요청 응답. 앱 ProposalResponse와 wire 형식만 동일하다."""

    id: int
    title: str
    content: str
    deadline: datetime
    errand_fee: int = Field(..., serialization_alias="errandFee")
    status: ProposalStatus

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AdminProposalReportResponse(BaseModel):
    """관리자 신고 응답. 앱 ProposalReportResponse와 wire 형식만 동일하다."""

    id: int
    proposal_id: int = Field(..., serialization_alias="proposalId")
    reporter_id: str = Field(..., serialization_alias="reporterId")
    reporter_name: str = Field(
        ...,
        serialization_alias="reporterName",
        description="신고자 이름. 이름이 없으면 관리자 표시용 '탈퇴한 사용자'를 반환한다.",
    )
    reason_question_id: int = Field(..., serialization_alias="reasonQuestionId")
    reason_question_text: str = Field(..., serialization_alias="reasonQuestionText")
    detail_reason: str | None = Field(None, serialization_alias="detailReason")
    status: ProposalReportStatus
    created_at: datetime = Field(..., serialization_alias="createdAt")
    reviewed_at: datetime | None = Field(None, serialization_alias="reviewedAt")
    proposal_status: ProposalStatus | None = Field(None, serialization_alias="proposalStatus")

    model_config = ConfigDict(populate_by_name=True)


class AdminNoteRequest(BaseModel):
    """관리자 메모만 받는 처리 요청. 취소·반려·지급에 공용으로 쓴다."""

    admin_note: str | None = Field(
        None,
        max_length=500,
        validation_alias="adminNote",
        description="관리자 메모",
    )
    admin_id: str | None = Field(
        None,
        max_length=36,
        validation_alias="adminId",
        description="처리한 관리자 식별자",
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AdminRefundVoidRequest(BaseModel):
    """입금 대조 결과 입금이 없어 환불 없이 종결하는 요청.

    돈을 지급하지 않고 종결하는 유일한 경로라 근거를 남기도록 메모를 필수로 받는다.
    """

    admin_note: str = Field(
        ...,
        min_length=1,
        max_length=200,
        validation_alias="adminNote",
        description="입금이 없다고 판단한 근거",
    )
    admin_id: str | None = Field(
        None,
        max_length=36,
        validation_alias="adminId",
        description="처리한 관리자 식별자",
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AdminDisputeResolveRequest(BaseModel):
    """분쟁 판정 요청."""

    outcome: MissionResolution = Field(
        ...,
        description="판정 결과. COMPLETED는 임무 완료(꼬붕 수행비 지급 대상), FAILED는 임무 실패(행님 환불 대상)다.",
    )
    admin_note: str | None = Field(None, max_length=500, validation_alias="adminNote", description="관리자 메모")
    admin_id: str | None = Field(None, max_length=36, validation_alias="adminId", description="처리한 관리자 식별자")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AdminProposalSummaryResponse(BaseModel):
    """관리자 요청 목록 항목."""

    id: int
    orderer_id: str = Field(..., serialization_alias="ordererId")
    orderer_name: str = Field(
        ...,
        serialization_alias="ordererName",
        description="행님 이름. 이름이 없으면 관리자 표시용 '탈퇴한 사용자'를 반환한다.",
    )
    errand_fee: int = Field(..., serialization_alias="errandFee")
    status: ProposalStatus
    offer_count: int = Field(..., serialization_alias="offerCount")
    created_at: datetime = Field(..., serialization_alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AdminProposalDetailResponse(BaseModel):
    """관리자 요청 상세."""

    id: int
    title: str
    content: str
    deadline: datetime
    errand_fee: int = Field(..., serialization_alias="errandFee")
    orderer_id: str = Field(..., serialization_alias="ordererId")
    orderer_name: str = Field(
        ...,
        serialization_alias="ordererName",
        description="행님 이름. 이름이 없으면 관리자 표시용 '탈퇴한 사용자'를 반환한다.",
    )
    orderer_level: int = Field(0, serialization_alias="ordererLevel")
    status: ProposalStatus
    created_at: datetime = Field(..., serialization_alias="createdAt")
    open_chat_url: str | None = Field(None, serialization_alias="openChatUrl")
    accepted_offer_id: int | None = Field(None, serialization_alias="acceptedOfferId")
    accepted_runner_name: str | None = Field(None, serialization_alias="acceptedRunnerName")
    mission_id: int | None = Field(None, serialization_alias="missionId")
    admin_note: str | None = Field(None, serialization_alias="adminNote")
    depositor_name: str | None = Field(
        None,
        serialization_alias="depositorName",
        description="행님이 기재한 입금자명. 현재 이 값을 수집하는 경로가 없어 항상 null이다.",
    )
    deposit_bank_name: str | None = Field(
        None,
        serialization_alias="depositBankName",
        description="플랫폼 입금 계좌 은행. 운영 설정값에서 읽는다.",
    )
    deposit_account_number: str | None = Field(None, serialization_alias="depositAccountNumber")
    deposit_account_holder: str | None = Field(None, serialization_alias="depositAccountHolder")
    matched_at: datetime | None = Field(None, serialization_alias="matchedAt")
    runner_confirmed_at: datetime | None = Field(None, serialization_alias="runnerConfirmedAt")
    orderer_confirmed_at: datetime | None = Field(None, serialization_alias="ordererConfirmedAt")
    disputed_at: datetime | None = Field(None, serialization_alias="disputedAt")
    resolved_at: datetime | None = Field(None, serialization_alias="resolvedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AdminOfferSummaryResponse(BaseModel):
    """관리자 지원 목록 항목."""

    id: int
    proposal_id: int = Field(..., serialization_alias="proposalId")
    runner_id: str = Field(..., serialization_alias="runnerId")
    runner_name: str = Field(
        ...,
        serialization_alias="runnerName",
        description="꼬붕 이름. 이름이 없으면 관리자 표시용 '탈퇴한 사용자'를 반환한다.",
    )
    runner_level: int = Field(0, serialization_alias="runnerLevel")
    status: OfferStatus
    accepted: bool = Field(..., description="수락된 지원인지 여부")
    has_dispute: bool = Field(..., serialization_alias="hasDispute")
    amount: int = Field(
        ...,
        description="요청의 수행비. 지원에는 금액 개념이 없어 요청 금액을 그대로 내려준다.",
    )
    open_chat_url: str | None = Field(None, serialization_alias="openChatUrl")
    created_at: datetime = Field(..., serialization_alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AdminDisputeSummaryResponse(BaseModel):
    """관리자 분쟁 목록 항목."""

    id: int
    proposal_id: int = Field(..., serialization_alias="proposalId")
    offer_id: int = Field(..., serialization_alias="offerId")
    mission_id: int = Field(..., serialization_alias="missionId")
    requester_id: str = Field(..., serialization_alias="requesterId")
    requester_name: str = Field(
        ...,
        serialization_alias="requesterName",
        description="신청자 이름. 이름이 없으면 관리자 표시용 '탈퇴한 사용자'를 반환한다.",
    )
    requester_role: str = Field(..., serialization_alias="requesterRole", description="ORDERER 또는 RUNNER")
    status: DisputeProcessStatus
    created_at: datetime = Field(..., serialization_alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AdminDisputeDetailResponse(BaseModel):
    """관리자 분쟁 상세."""

    id: int
    proposal_id: int = Field(..., serialization_alias="proposalId")
    offer_id: int = Field(..., serialization_alias="offerId")
    mission_id: int = Field(..., serialization_alias="missionId")
    requester_id: str = Field(..., serialization_alias="requesterId")
    requester_name: str = Field(
        ...,
        serialization_alias="requesterName",
        description="신청자 이름. 이름이 없으면 관리자 표시용 '탈퇴한 사용자'를 반환한다.",
    )
    requester_role: str = Field(..., serialization_alias="requesterRole", description="ORDERER 또는 RUNNER")
    status: DisputeProcessStatus
    created_at: datetime = Field(..., serialization_alias="createdAt")
    target_id: str = Field(..., serialization_alias="targetId")
    target_name: str = Field(
        ...,
        serialization_alias="targetName",
        description="상대방 이름. 이름이 없으면 관리자 표시용 '탈퇴한 사용자'를 반환한다.",
    )
    target_role: str = Field(..., serialization_alias="targetRole")
    reason_question_id: int = Field(..., serialization_alias="reasonQuestionId")
    reason_question_text: str = Field(..., serialization_alias="reasonQuestionText")
    detail_reason: str | None = Field(None, serialization_alias="detailReason")
    proposal_status: ProposalStatus = Field(..., serialization_alias="proposalStatus")
    offer_status: OfferStatus = Field(..., serialization_alias="offerStatus")
    admin_note: str | None = Field(None, serialization_alias="adminNote")
    resolved_at: datetime | None = Field(None, serialization_alias="resolvedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AdminRefundSummaryResponse(BaseModel):
    """관리자 환불 목록 항목. 식별자는 Refund ID다."""

    id: int
    proposal_id: int = Field(..., serialization_alias="proposalId")
    proposal_status: ProposalStatus = Field(..., serialization_alias="proposalStatus")
    orderer_id: str = Field(..., serialization_alias="ordererId")
    orderer_name: str = Field(
        ...,
        serialization_alias="ordererName",
        description="행님 이름. 이름이 없으면 관리자 표시용 '탈퇴한 사용자'를 반환한다.",
    )
    amount: int
    status: RefundStatus
    reason: RefundReason
    requested_at: datetime = Field(..., serialization_alias="requestedAt", description="환불 대상이 된 시각")
    processed_at: datetime | None = Field(None, serialization_alias="processedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AdminRefundDetailResponse(BaseModel):
    """관리자 환불 상세. reason은 원인 코드이고 reasonDetail은 입력된 상세 사유다."""

    id: int
    proposal_id: int = Field(..., serialization_alias="proposalId")
    proposal_status: ProposalStatus = Field(..., serialization_alias="proposalStatus")
    orderer_id: str = Field(..., serialization_alias="ordererId")
    orderer_name: str = Field(
        ...,
        serialization_alias="ordererName",
        description="행님 이름. 이름이 없으면 관리자 표시용 '탈퇴한 사용자'를 반환한다.",
    )
    amount: int
    status: RefundStatus
    requested_at: datetime = Field(..., serialization_alias="requestedAt")
    processed_at: datetime | None = Field(None, serialization_alias="processedAt")
    reason: RefundReason
    reason_detail: str | None = Field(None, serialization_alias="reasonDetail")
    refund_bank_name: str | None = Field(
        None,
        serialization_alias="refundBankName",
        description="현재 환불 계좌의 은행명. 탈퇴로 계좌 행이 삭제됐거나 레거시 데이터면 null이다.",
    )
    refund_account_number: str | None = Field(
        None,
        serialization_alias="refundAccountNumber",
        description="현재 환불 계좌번호. 탈퇴로 계좌 행이 삭제됐거나 레거시 데이터면 null이다.",
    )
    refund_account_holder: str | None = Field(
        None,
        serialization_alias="refundAccountHolder",
        description="현재 환불 계좌 예금주. 탈퇴로 계좌 행이 삭제됐거나 레거시 데이터면 null이다.",
    )
    admin_note: str | None = Field(None, serialization_alias="adminNote")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AdminPayoutDetailResponse(BaseModel):
    """관리자 수행비 지급 상세. 계좌번호는 관리자용 비마스킹 값이다."""

    id: int
    proposal_id: int = Field(..., serialization_alias="proposalId")
    offer_id: int = Field(..., serialization_alias="offerId")
    runner_id: str = Field(..., serialization_alias="runnerId")
    runner_name: str = Field(
        ...,
        serialization_alias="runnerName",
        description="꼬붕 이름. 이름이 없으면 관리자 표시용 '탈퇴한 사용자'를 반환한다.",
    )
    amount: int
    status: PayoutStatus
    settled_at: datetime | None = Field(None, serialization_alias="settledAt")
    payout_bank_name: str | None = Field(
        None,
        serialization_alias="payoutBankName",
        description="현재 지급 계좌의 은행명. 계좌 미등록 또는 탈퇴로 계좌 행이 없으면 null이다.",
    )
    payout_account_number: str | None = Field(
        None,
        serialization_alias="payoutAccountNumber",
        description="현재 지급 계좌번호. 계좌 미등록 또는 탈퇴로 계좌 행이 없으면 null이다.",
    )
    payout_account_holder: str | None = Field(
        None,
        serialization_alias="payoutAccountHolder",
        description="현재 지급 계좌 예금주. 계좌 미등록 또는 탈퇴로 계좌 행이 없으면 null이다.",
    )
    admin_note: str | None = Field(None, serialization_alias="adminNote")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AdminUserSummaryResponse(BaseModel):
    """관리자 사용자 목록 항목. 관리자 계정은 목록에 넣지 않는다."""

    id: str = Field(..., description="사용자 ID")
    name: str = Field(
        ...,
        description="사용자 이름. 이름이 없으면 관리자 표시용 '탈퇴한 사용자'를 반환한다.",
    )
    created_at: datetime = Field(..., serialization_alias="createdAt", description="회원 가입일")
    mission_count: int = Field(
        ...,
        serialization_alias="missionCount",
        description="임무 수행 횟수. 성공 완료한 꼬붕 지원 수(users.level)와 같은 값이다.",
    )

    model_config = ConfigDict(populate_by_name=True)


class AdminSummaryResponse(BaseModel):
    """대시보드 미처리 건수 집계."""

    unpaid_count: int = Field(..., serialization_alias="unpaidCount", description="입금 확인이 필요한 요청 수")
    dispute_count: int = Field(..., serialization_alias="disputeCount", description="미처리 분쟁 수")
    refund_count: int = Field(..., serialization_alias="refundCount", description="미처리 환불 수")
    deposit_review_count: int = Field(
        ..., serialization_alias="depositReviewCount", description="입금 대조 대기 환불 수"
    )
    settlement_count: int = Field(..., serialization_alias="settlementCount", description="미처리 수행비 지급 수")
    report_count: int = Field(..., serialization_alias="reportCount", description="미처리 신고 수")

    model_config = ConfigDict(populate_by_name=True)


__all__ = [
    "AdminConfirmPaymentRequest",
    "AdminLoginRequest",
    "AdminDisputeDetailResponse",
    "AdminDisputeResolveRequest",
    "AdminDisputeSummaryResponse",
    "AdminNoteRequest",
    "AdminOfferSummaryResponse",
    "AdminPayoutDetailResponse",
    "AdminProposalReportResponse",
    "AdminProposalResponse",
    "AdminProposalDetailResponse",
    "AdminProposalSummaryResponse",
    "AdminRefundDetailResponse",
    "AdminRefundVoidRequest",
    "AdminRefundSummaryResponse",
    "AdminSummaryResponse",
    "AdminUserSummaryResponse",
    "ORDERER_ROLE",
    "RUNNER_ROLE",
]
