"""Mission request and response schemas for the admin console."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.mission import MissionResolution, MissionStatus, PayoutStatus


class MissionResolveRequest(BaseModel):
    """Admin verdict for a disputed mission."""

    resolution: MissionResolution = Field(
        ...,
        description="분쟁 판정 결과. COMPLETED는 꼬붕 수행비 지급 대상, FAILED는 행님 환불 대상이다.",
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MissionPayoutRequest(BaseModel):
    """Record of an already executed transfer. 금액은 요청의 수행비 전액으로 서버가 정한다."""

    admin_id: str | None = Field(
        None,
        max_length=36,
        validation_alias="adminId",
        description="처리한 관리자 식별자",
    )
    memo: str | None = Field(None, max_length=200, description="이체 참조번호 등 메모")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MissionResponse(BaseModel):
    """Mission API response. 관리자 웹 전용이며 앱에는 노출하지 않는다."""

    id: int
    proposal_id: int = Field(..., serialization_alias="proposalId")
    offer_id: int = Field(..., serialization_alias="offerId")
    orderer_id: str = Field(..., serialization_alias="ordererId")
    orderer_name: str = Field(
        ...,
        serialization_alias="ordererName",
        description="행님 이름. 이름이 없으면 관리자 표시용 '탈퇴한 사용자'를 반환한다.",
    )
    runner_id: str = Field(..., serialization_alias="runnerId")
    runner_name: str = Field(
        ...,
        serialization_alias="runnerName",
        description="꼬붕 이름. 이름이 없으면 관리자 표시용 '탈퇴한 사용자'를 반환한다.",
    )
    open_chat_url: str | None = Field(
        None,
        serialization_alias="openChatUrl",
        description="매칭 당사자의 카카오톡 오픈채팅방 링크. 저장된 링크가 없으면 null이다.",
    )
    status: MissionStatus
    errand_fee: int = Field(..., serialization_alias="errandFee")
    settlement_paid: bool = Field(..., serialization_alias="settlementPaid", description="꼬붕 수행비 입금 여부")
    settlement_status: PayoutStatus = Field(
        ...,
        serialization_alias="settlementStatus",
        description="수행비 지급 처리 상태",
    )
    resolution: MissionResolution | None = None
    started_at: datetime = Field(..., serialization_alias="startedAt")
    runner_confirmed_at: datetime | None = Field(
        None,
        serialization_alias="runnerConfirmedAt",
        description="꼬붕이 수행 완료를 누른 시각. null이면 아직 누르지 않았다.",
    )
    orderer_confirmed_at: datetime | None = Field(
        None,
        serialization_alias="ordererConfirmedAt",
        description="행님이 수령을 확인한 시각. null이면 아직 누르지 않았다.",
    )
    disputed_at: datetime | None = Field(None, serialization_alias="disputedAt")
    completed_at: datetime | None = Field(None, serialization_alias="completedAt")
    failed_at: datetime | None = Field(None, serialization_alias="failedAt")
    resolved_at: datetime | None = Field(None, serialization_alias="resolvedAt")
    resolved_by_admin_id: str | None = Field(None, serialization_alias="resolvedByAdminId")
    settlement_paid_at: datetime | None = Field(None, serialization_alias="settlementPaidAt")
    settlement_paid_by_admin_id: str | None = Field(None, serialization_alias="settlementPaidByAdminId")
    payout_memo: str | None = Field(None, serialization_alias="payoutMemo")
    created_at: datetime = Field(..., serialization_alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


__all__ = ["MissionPayoutRequest", "MissionResolveRequest", "MissionResponse"]
