"""Admin API router."""
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.security import require_admin
from app.core.firebase import get_notification_worker
from app.core.errors import AppError
from app.core.openapi import (
    ADMIN_DISPUTE_DETAIL_RESPONSE_EXAMPLE,
    ADMIN_DISPUTE_PAGE_EXAMPLE,
    ADMIN_DISPUTE_REJECTED_EXAMPLE,
    ADMIN_DISPUTE_RESOLVED_EXAMPLE,
    ADMIN_OFFER_PAGE_EXAMPLE,
    ADMIN_PAYOUT_COMPLETED_EXAMPLE,
    ADMIN_PAYOUT_DETAIL_RESPONSE_EXAMPLE,
    ADMIN_PAYOUT_PAGE_EXAMPLE,
    ADMIN_PAYOUT_REJECTED_EXAMPLE,
    ADMIN_PROPOSAL_CANCELLED_EXAMPLE,
    ADMIN_PROPOSAL_DETAIL_RESPONSE_EXAMPLE,
    ADMIN_PROPOSAL_PAGE_EXAMPLE,
    ADMIN_REFUND_COMPLETED_EXAMPLE,
    ADMIN_REFUND_DETAIL_RESPONSE_EXAMPLE,
    ADMIN_REFUND_PAGE_EXAMPLE,
    ADMIN_SUMMARY_EXAMPLE,
    MISSION_DETAIL_EXAMPLES,
    MISSION_PAGE_EXAMPLES,
    MISSION_RESOLVED_EXAMPLES,
    MISSION_SETTLEMENT_EXAMPLE,
    PROPOSAL_EXAMPLE,
    PROPOSAL_REPORT_ACCEPTED_EXAMPLE,
    PROPOSAL_REPORT_PAGE_EXAMPLES,
    PROPOSAL_REPORT_REJECTED_EXAMPLE,
    error_responses,
    success_response,
    success_response_examples,
)
from app.models.dispute_evidence import DisputeProcessStatus
from app.models.mission import MissionStatus, PayoutStatus
from app.models.offer import OfferStatus
from app.models.proposal import ProposalStatus
from app.models.refund import RefundStatus
from app.schemas.admin import (
    AdminConfirmPaymentRequest,
    AdminDisputeDetailResponse,
    AdminDisputeResolveRequest,
    AdminDisputeSummaryResponse,
    AdminNoteRequest,
    AdminOfferSummaryResponse,
    AdminPayoutDetailResponse,
    AdminProposalReportResponse,
    AdminProposalResponse,
    AdminProposalDetailResponse,
    AdminProposalSummaryResponse,
    AdminRefundDetailResponse,
    AdminRefundSummaryResponse,
    AdminSummaryResponse,
)
from app.services.admin.admin_command_service import AdminCommandService
from app.services.admin.admin_query_service import AdminQueryService
from app.schemas.mission import MissionPayoutRequest, MissionResolveRequest, MissionResponse
from app.schemas.common import ApiResponse
from app.schemas.common import PageResponse
from app.models.proposal_report import ProposalReportStatus
from app.services.mission.mission_service import MissionService
from app.services.notification_outbox import pop_pending_notification_ids
from app.services.proposal.proposal_service import ProposalService
from app.services.proposal.proposal_report_service import ProposalReportService


#: 관리자 API는 전부 관리자 계정 토큰을 요구한다. 로그인 경로만 별도 라우터로 열려 있다.
router = APIRouter(
    prefix="/admin",
    tags=["관리자"],
    dependencies=[Depends(require_admin)],
    responses=error_responses(AppError.INVALID_TOKEN, AppError.FORBIDDEN),
)


def _queue_created_notifications(background_tasks: BackgroundTasks, db: Session) -> None:
    notification_ids = pop_pending_notification_ids(db)
    if notification_ids:
        background_tasks.add_task(get_notification_worker().flush_pending, SessionLocal, notification_ids)


@router.get(
    "/proposal-reports",
    response_model=ApiResponse[PageResponse[AdminProposalReportResponse]],
    summary="게시글 신고 목록 조회 (관리자 전용)",
    responses={200: success_response_examples(PROPOSAL_REPORT_PAGE_EXAMPLES)},
)
def list_proposal_reports(
    report_status: ProposalReportStatus | None = Query(None, alias="status"),
    proposal_id: int | None = Query(None, alias="proposalId", description="특정 요청의 신고만 조회"),
    keyword: str | None = Query(None, description="신고 ID·요청 ID·신고자 ID·사유·상세 내용 검색"),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ApiResponse[PageResponse[AdminProposalReportResponse]]:
    return ApiResponse(
        success=True,
        data=ProposalReportService.list_reports(db, report_status, page, size, proposal_id, keyword),
    )


@router.post(
    "/proposal-reports/{report_id}/accept",
    response_model=ApiResponse[AdminProposalReportResponse],
    summary="게시글 신고 승인 (관리자 전용)",
    responses={
        200: success_response(PROPOSAL_REPORT_ACCEPTED_EXAMPLE),
        **error_responses(AppError.PROPOSAL_REPORT_NOT_FOUND, AppError.PROPOSAL_REPORT_NOT_REVIEWABLE, AppError.PROPOSAL_NOT_REPORTABLE),
    },
)
def accept_proposal_report(report_id: int, db: Session = Depends(get_db)) -> ApiResponse[AdminProposalReportResponse]:
    return ApiResponse(success=True, data=ProposalReportService.accept(db, report_id), message="신고가 승인되었습니다.")


@router.post(
    "/proposal-reports/{report_id}/reject",
    response_model=ApiResponse[AdminProposalReportResponse],
    summary="게시글 신고 반려 (관리자 전용)",
    responses={
        200: success_response(PROPOSAL_REPORT_REJECTED_EXAMPLE),
        **error_responses(AppError.PROPOSAL_REPORT_NOT_FOUND, AppError.PROPOSAL_REPORT_NOT_REVIEWABLE),
    },
)
def reject_proposal_report(report_id: int, db: Session = Depends(get_db)) -> ApiResponse[AdminProposalReportResponse]:
    return ApiResponse(success=True, data=ProposalReportService.reject(db, report_id), message="신고가 반려되었습니다.")


@router.post(
    "/proposal/{proposal_id}/confirm-payment",
    response_model=ApiResponse[AdminProposalResponse],
    status_code=status.HTTP_200_OK,
    summary="입금 확인 (관리자 전용)",
    description="관리자가 오더러의 입금을 확인하여 요청을 POSTED 상태로 전환합니다.",
    responses={
        200: success_response({"success": True, "data": PROPOSAL_EXAMPLE, "message": None}),
        **error_responses(
            AppError.VALIDATION_ERROR,
            AppError.PROPOSAL_NOT_FOUND,
            AppError.INVALID_STATUS,
        ),
    },
)
def confirm_payment(
    proposal_id: int,
    request: AdminConfirmPaymentRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """입금을 확인해 요청을 POSTED로 전환하고 오픈채팅방 URL을 함께 저장한다."""
    proposal = ProposalService.confirm_payment(
        db=db,
        proposal_id=proposal_id,
        open_chat_url=request.open_chat_url,
    )
    _queue_created_notifications(background_tasks, db)

    return ApiResponse(
        success=True,
        data=AdminProposalResponse.model_validate(proposal),
    )


@router.get(
    "/proposal/pending-payment",
    response_model=ApiResponse[PageResponse[AdminProposalSummaryResponse]],
    summary="입금 대기 중인 요청 목록 조회 (관리자 전용)",
    description=(
        "입금 대기(HOLDING) 상태인 요청을 조회합니다. "
        "`GET /v1/admin/proposal?status=HOLDING`으로 대체 가능하며 이 경로는 유지 보수만 합니다."
    ),
    deprecated=True,
    responses={200: success_response(ADMIN_PROPOSAL_PAGE_EXAMPLE)},
)
def list_pending_payment_proposals(
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ApiResponse[PageResponse[AdminProposalSummaryResponse]]:
    return ApiResponse(
        success=True,
        data=AdminQueryService.list_proposals(db, [ProposalStatus.HOLDING], None, page, size),
    )


@router.get(
    "/missions",
    response_model=ApiResponse[PageResponse[MissionResponse]],
    status_code=status.HTTP_200_OK,
    summary="미션 목록 조회 (관리자 전용)",
    description=(
        "관리자가 미션을 상태로 필터링해 조회합니다. "
        "`status=STARTED&status=DISPUTED`처럼 반복 지정할 수 있습니다."
    ),
    responses={200: success_response_examples(MISSION_PAGE_EXAMPLES)},
)
def list_missions(
    mission_statuses: list[MissionStatus] | None = Query(
        None,
        alias="status",
        description="미션 상태 필터. `status=A&status=B`처럼 반복 지정합니다.",
    ),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ApiResponse[PageResponse[MissionResponse]]:
    return ApiResponse(success=True, data=MissionService.search(db, mission_statuses, page, size))


@router.get(
    "/missions/{mission_id}",
    response_model=ApiResponse[MissionResponse],
    status_code=status.HTTP_200_OK,
    summary="미션 상세 조회 (관리자 전용)",
    description="관리자가 미션 한 건의 상태와 지급·환불 여부를 조회합니다.",
    responses={
        200: success_response_examples(MISSION_DETAIL_EXAMPLES),
        **error_responses(AppError.MISSION_NOT_FOUND),
    },
)
def get_mission(mission_id: int, db: Session = Depends(get_db)) -> ApiResponse[MissionResponse]:
    return ApiResponse(success=True, data=MissionService.get_detail(db, mission_id))


@router.post(
    "/missions/{mission_id}/resolve",
    response_model=ApiResponse[MissionResponse],
    status_code=status.HTTP_200_OK,
    summary="미션 분쟁 판정 (관리자 전용)",
    description=(
        "관리자가 분쟁 중인 미션을 완료 또는 실패로 판정하고 요청과 지원을 함께 종결합니다. "
        "완료는 꼬붕 수행비 지급 대상, 실패는 행님 환불 대상이 됩니다."
    ),
    responses={
        200: success_response_examples(MISSION_RESOLVED_EXAMPLES),
        **error_responses(
            AppError.MISSION_NOT_FOUND,
            AppError.MISSION_NOT_RESOLVABLE,
            AppError.OFFER_NOT_FOUND,
            AppError.PROPOSAL_NOT_FOUND,
            AppError.VALIDATION_ERROR,
        ),
    },
)
def resolve_mission(
    mission_id: int,
    request: MissionResolveRequest,
    db: Session = Depends(get_db),
) -> ApiResponse[MissionResponse]:
    mission = MissionService.resolve_dispute(db, mission_id=mission_id, resolution=request.resolution)
    return ApiResponse(success=True, data=mission, message="미션 분쟁이 해결되었습니다.")


@router.post(
    "/missions/{mission_id}/settlement",
    response_model=ApiResponse[MissionResponse],
    status_code=status.HTTP_200_OK,
    summary="수행비 지급 기록 (관리자 전용)",
    description=(
        "관리자가 꼬붕에게 수행비를 이체한 사실을 기록해 미션을 입금 완료로 전환합니다. "
        "지급액은 요청의 수행비 전액이며 요청 본문으로 받지 않습니다."
    ),
    responses={
        200: success_response(MISSION_SETTLEMENT_EXAMPLE),
        **error_responses(
            AppError.MISSION_NOT_FOUND,
            AppError.MISSION_NOT_SETTLEABLE,
            AppError.VALIDATION_ERROR,
        ),
    },
)
def record_mission_settlement(
    mission_id: int,
    request: MissionPayoutRequest | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[MissionResponse]:
    payout = request or MissionPayoutRequest()
    mission = MissionService.record_settlement(
        db,
        mission_id=mission_id,
        admin_id=payout.admin_id,
        memo=payout.memo,
    )
    return ApiResponse(success=True, data=mission, message="수행비 지급을 기록했습니다.")


@router.get(
    "/summary",
    response_model=ApiResponse[AdminSummaryResponse],
    summary="대시보드 집계 조회 (관리자 전용)",
    description="관리자가 처리해야 할 미처리 건수를 항목별로 집계합니다.",
    responses={200: success_response(ADMIN_SUMMARY_EXAMPLE)},
)
def get_admin_summary(db: Session = Depends(get_db)) -> ApiResponse[AdminSummaryResponse]:
    return ApiResponse(success=True, data=AdminQueryService.summary(db))


@router.get(
    "/proposal",
    response_model=ApiResponse[PageResponse[AdminProposalSummaryResponse]],
    summary="요청 목록 조회 (관리자 전용)",
    description="관리자가 요청을 상태와 키워드로 필터링해 조회합니다. `status=A&status=B`처럼 반복 지정할 수 있습니다.",
    responses={200: success_response(ADMIN_PROPOSAL_PAGE_EXAMPLE)},
)
def list_admin_proposals(
    proposal_statuses: list[ProposalStatus] | None = Query(None, alias="status"),
    keyword: str | None = Query(None, description="요청 ID 또는 행님 이름 검색"),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ApiResponse[PageResponse[AdminProposalSummaryResponse]]:
    return ApiResponse(
        success=True,
        data=AdminQueryService.list_proposals(db, proposal_statuses, keyword, page, size),
    )


@router.get(
    "/proposal/{proposal_id}",
    response_model=ApiResponse[AdminProposalDetailResponse],
    summary="요청 상세 조회 (관리자 전용)",
    description="관리자가 요청 한 건의 상세와 선택된 지원·미션·입금 계좌 정보를 조회합니다.",
    responses={
        200: success_response(ADMIN_PROPOSAL_DETAIL_RESPONSE_EXAMPLE),
        **error_responses(AppError.PROPOSAL_NOT_FOUND),
    },
)
def get_admin_proposal(proposal_id: int, db: Session = Depends(get_db)) -> ApiResponse[AdminProposalDetailResponse]:
    return ApiResponse(success=True, data=AdminQueryService.get_proposal_detail(db, proposal_id))


@router.post(
    "/proposal/{proposal_id}/cancel",
    response_model=ApiResponse[AdminProposalDetailResponse],
    summary="요청 취소 (관리자 전용)",
    description=(
        "관리자가 요청을 취소하고 연결된 지원을 함께 취소합니다. "
        "진행 중인 미션이 있으면 환불 대상인 실패로 종결합니다."
    ),
    responses={
        200: success_response(ADMIN_PROPOSAL_CANCELLED_EXAMPLE),
        **error_responses(AppError.PROPOSAL_NOT_FOUND, AppError.PROPOSAL_NOT_CANCELLABLE, AppError.VALIDATION_ERROR),
    },
)
def cancel_admin_proposal(
    proposal_id: int,
    request: AdminNoteRequest | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[AdminProposalDetailResponse]:
    payload = request or AdminNoteRequest()
    return ApiResponse(
        success=True,
        data=AdminCommandService.cancel_proposal(db, proposal_id, payload.admin_note),
        message="요청이 취소되었습니다.",
    )


@router.get(
    "/offer",
    response_model=ApiResponse[PageResponse[AdminOfferSummaryResponse]],
    summary="지원 목록 조회 (관리자 전용)",
    description=(
        "관리자가 지원을 요청·상태·수락 여부·분쟁 여부로 필터링해 조회합니다. "
        "지원에는 금액 개념이 없어 `amount`는 요청의 수행비를 그대로 내려줍니다."
    ),
    responses={200: success_response(ADMIN_OFFER_PAGE_EXAMPLE)},
)
def list_admin_offers(
    proposal_id: int | None = Query(None, alias="proposalId"),
    offer_statuses: list[OfferStatus] | None = Query(None, alias="status"),
    accepted: bool | None = Query(None, description="수락된 지원만 또는 그 외만 조회"),
    has_dispute: bool | None = Query(None, alias="hasDispute"),
    keyword: str | None = Query(None, description="지원 ID·요청 ID·꼬붕 이름 검색"),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ApiResponse[PageResponse[AdminOfferSummaryResponse]]:
    return ApiResponse(
        success=True,
        data=AdminQueryService.list_offers(
            db, proposal_id, offer_statuses, accepted, has_dispute, keyword, page, size
        ),
    )


@router.get(
    "/dispute",
    response_model=ApiResponse[PageResponse[AdminDisputeSummaryResponse]],
    summary="분쟁 목록 조회 (관리자 전용)",
    description="관리자가 분쟁을 처리 상태와 키워드로 필터링해 조회합니다. 처리 상태는 요청·지원의 진행 상태와 다른 축입니다.",
    responses={200: success_response(ADMIN_DISPUTE_PAGE_EXAMPLE)},
)
def list_admin_disputes(
    dispute_statuses: list[DisputeProcessStatus] | None = Query(None, alias="status"),
    proposal_id: int | None = Query(None, alias="proposalId"),
    keyword: str | None = Query(None, description="분쟁 ID·요청 ID·지원 ID·신청자 이름 검색"),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ApiResponse[PageResponse[AdminDisputeSummaryResponse]]:
    return ApiResponse(
        success=True,
        data=AdminQueryService.list_disputes(db, dispute_statuses, proposal_id, keyword, page, size),
    )


@router.get(
    "/dispute/{dispute_id}",
    response_model=ApiResponse[AdminDisputeDetailResponse],
    summary="분쟁 상세 조회 (관리자 전용)",
    description="관리자가 분쟁 한 건의 신청자·대상자와 사유, 처리 상태를 조회합니다.",
    responses={
        200: success_response(ADMIN_DISPUTE_DETAIL_RESPONSE_EXAMPLE),
        **error_responses(
            AppError.DISPUTE_EVIDENCE_NOT_FOUND,
            AppError.PROPOSAL_NOT_FOUND,
            AppError.OFFER_NOT_FOUND,
        ),
    },
)
def get_admin_dispute(dispute_id: int, db: Session = Depends(get_db)) -> ApiResponse[AdminDisputeDetailResponse]:
    return ApiResponse(success=True, data=AdminQueryService.get_dispute_detail(db, dispute_id))


@router.post(
    "/dispute/{dispute_id}/resolve",
    response_model=ApiResponse[AdminDisputeDetailResponse],
    summary="분쟁 판정 (관리자 전용)",
    description=(
        "관리자가 분쟁을 판정하고 요청·지원·미션을 함께 종결합니다. "
        "`COMPLETED`는 꼬붕 수행비 지급 대상, `FAILED`는 행님 환불 대상이 됩니다."
    ),
    responses={
        200: success_response(ADMIN_DISPUTE_RESOLVED_EXAMPLE),
        **error_responses(
            AppError.DISPUTE_EVIDENCE_NOT_FOUND,
            AppError.DISPUTE_ALREADY_REVIEWED,
            AppError.PROPOSAL_NOT_FOUND,
            AppError.OFFER_NOT_FOUND,
            AppError.MISSION_NOT_FOUND,
            AppError.MISSION_NOT_RESOLVABLE,
            AppError.VALIDATION_ERROR,
        ),
    },
)
def resolve_admin_dispute(
    dispute_id: int,
    request: AdminDisputeResolveRequest,
    db: Session = Depends(get_db),
) -> ApiResponse[AdminDisputeDetailResponse]:
    return ApiResponse(
        success=True,
        data=AdminCommandService.resolve_dispute(
            db, dispute_id, request.outcome, request.admin_id, request.admin_note
        ),
        message="분쟁이 처리되었습니다.",
    )


@router.post(
    "/dispute/{dispute_id}/reject",
    response_model=ApiResponse[AdminDisputeDetailResponse],
    summary="분쟁 반려 (관리자 전용)",
    description="관리자가 분쟁을 반려합니다. 요청·지원·미션 상태는 바뀌지 않습니다.",
    responses={
        200: success_response(ADMIN_DISPUTE_REJECTED_EXAMPLE),
        **error_responses(
            AppError.DISPUTE_EVIDENCE_NOT_FOUND,
            AppError.DISPUTE_ALREADY_REVIEWED,
            AppError.PROPOSAL_NOT_FOUND,
            AppError.OFFER_NOT_FOUND,
            AppError.VALIDATION_ERROR,
        ),
    },
)
def reject_admin_dispute(
    dispute_id: int,
    request: AdminNoteRequest | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[AdminDisputeDetailResponse]:
    payload = request or AdminNoteRequest()
    return ApiResponse(
        success=True,
        data=AdminCommandService.reject_dispute(db, dispute_id, payload.admin_id, payload.admin_note),
        message="분쟁이 반려되었습니다.",
    )


@router.get(
    "/refund",
    response_model=ApiResponse[PageResponse[AdminRefundSummaryResponse]],
    summary="환불 목록 조회 (관리자 전용)",
    description=(
        "입금 확인 후 취소 또는 분쟁 실패로 생성된 환불을 조회합니다. 식별자는 Refund ID입니다."
    ),
    responses={200: success_response(ADMIN_REFUND_PAGE_EXAMPLE)},
)
def list_admin_refunds(
    refund_statuses: list[RefundStatus] | None = Query(None, alias="status"),
    requested_from: date | None = Query(None, alias="requestedFrom", description="YYYY-MM-DD. 이 날짜 이후 요청분"),
    keyword: str | None = Query(None, description="환불 ID·요청 ID·행님 이름 검색"),
    proposal_id: int | None = Query(None, alias="proposalId"),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ApiResponse[PageResponse[AdminRefundSummaryResponse]]:
    return ApiResponse(
        success=True,
        data=AdminQueryService.list_refunds(
            db, refund_statuses, requested_from, keyword, proposal_id, page, size
        ),
    )


@router.get(
    "/refund/{refund_id}",
    response_model=ApiResponse[AdminRefundDetailResponse],
    summary="환불 상세 조회 (관리자 전용)",
    description="관리자가 실제로 이체해야 하므로 행님의 환불 계좌번호를 마스킹하지 않고 내려줍니다.",
    responses={
        200: success_response(ADMIN_REFUND_DETAIL_RESPONSE_EXAMPLE),
        **error_responses(AppError.REFUND_NOT_FOUND),
    },
)
def get_admin_refund(refund_id: int, db: Session = Depends(get_db)) -> ApiResponse[AdminRefundDetailResponse]:
    return ApiResponse(success=True, data=AdminQueryService.get_refund_detail(db, refund_id))


@router.post(
    "/refund/{refund_id}/complete",
    response_model=ApiResponse[AdminRefundDetailResponse],
    summary="환불 완료 처리 (관리자 전용)",
    description="환불 완료를 기록하고 연결된 요청을 `REFUNDED`로 종결합니다.",
    responses={
        200: success_response(ADMIN_REFUND_COMPLETED_EXAMPLE),
        **error_responses(
            AppError.REFUND_NOT_FOUND,
            AppError.REFUND_NOT_PROCESSABLE,
            AppError.PROPOSAL_NOT_FOUND,
            AppError.VALIDATION_ERROR,
        ),
    },
)
def complete_admin_refund(
    refund_id: int,
    request: AdminNoteRequest | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[AdminRefundDetailResponse]:
    payload = request or AdminNoteRequest()
    return ApiResponse(
        success=True,
        data=AdminCommandService.complete_refund(db, refund_id, payload.admin_id, payload.admin_note),
        message="환불을 기록했습니다.",
    )


@router.get(
    "/payout",
    response_model=ApiResponse[PageResponse[MissionResponse]],
    summary="수행비 지급 목록 조회 (관리자 전용)",
    description="지급 대상 미션을 조회합니다. 식별자는 미션 ID이며 상태는 미션의 지급 기록에서 파생합니다.",
    responses={200: success_response(ADMIN_PAYOUT_PAGE_EXAMPLE)},
)
def list_admin_payouts(
    payout_statuses: list[PayoutStatus] | None = Query(None, alias="status"),
    proposal_id: int | None = Query(None, alias="proposalId"),
    keyword: str | None = Query(None, description="지급 ID·요청 ID·지원 ID·꼬붕 이름 검색"),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ApiResponse[PageResponse[MissionResponse]]:
    return ApiResponse(
        success=True,
        data=AdminQueryService.list_payouts(db, payout_statuses, proposal_id, keyword, page, size),
    )


@router.get(
    "/payout/{payout_id}",
    response_model=ApiResponse[AdminPayoutDetailResponse],
    summary="수행비 지급 상세 조회 (관리자 전용)",
    description="관리자가 실제로 이체해야 하므로 꼬붕의 정산 계좌번호를 마스킹하지 않고 내려줍니다.",
    responses={
        200: success_response(ADMIN_PAYOUT_DETAIL_RESPONSE_EXAMPLE),
        **error_responses(AppError.MISSION_NOT_FOUND),
    },
)
def get_admin_payout(payout_id: int, db: Session = Depends(get_db)) -> ApiResponse[AdminPayoutDetailResponse]:
    return ApiResponse(success=True, data=AdminQueryService.get_payout_detail(db, payout_id))


@router.post(
    "/payout/{payout_id}/complete",
    response_model=ApiResponse[AdminPayoutDetailResponse],
    summary="수행비 지급 완료 처리 (관리자 전용)",
    description="지급 완료를 기록합니다. 요청·지원 상태는 바뀌지 않습니다.",
    responses={
        200: success_response(ADMIN_PAYOUT_COMPLETED_EXAMPLE),
        **error_responses(AppError.MISSION_NOT_FOUND, AppError.MISSION_NOT_SETTLEABLE, AppError.VALIDATION_ERROR),
    },
)
def complete_admin_payout(
    payout_id: int,
    request: AdminNoteRequest | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[AdminPayoutDetailResponse]:
    payload = request or AdminNoteRequest()
    return ApiResponse(
        success=True,
        data=AdminCommandService.complete_payout(db, payout_id, payload.admin_id, payload.admin_note),
        message="수행비 지급을 기록했습니다.",
    )


@router.post(
    "/payout/{payout_id}/reject",
    response_model=ApiResponse[AdminPayoutDetailResponse],
    summary="수행비 지급 반려 (관리자 전용)",
    description="지급을 반려합니다. 요청·지원 상태는 바뀌지 않습니다.",
    responses={
        200: success_response(ADMIN_PAYOUT_REJECTED_EXAMPLE),
        **error_responses(AppError.MISSION_NOT_FOUND, AppError.MISSION_NOT_SETTLEABLE, AppError.VALIDATION_ERROR),
    },
)
def reject_admin_payout(
    payout_id: int,
    request: AdminNoteRequest | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[AdminPayoutDetailResponse]:
    payload = request or AdminNoteRequest()
    return ApiResponse(
        success=True,
        data=AdminCommandService.reject_payout(db, payout_id, payload.admin_id, payload.admin_note),
        message="수행비 지급을 반려했습니다.",
    )
