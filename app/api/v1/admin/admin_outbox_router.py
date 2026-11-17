"""관리자 Outbox API: DEAD 전달 조회와 수동 재처리 (OUTBOX-REQ-006, docs/design-docs/outbox.md)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.core.openapi import (
    ADMIN_OUTBOX_BULK_RETRY_EXAMPLE,
    ADMIN_OUTBOX_DELIVERY_PAGE_EXAMPLE,
    ADMIN_OUTBOX_RETRY_EXAMPLE,
    error_responses,
    success_response,
)
from app.core.security import require_admin
from app.core.time import to_utc_naive
from app.models.outbox import DeliveryStatus
from app.models.user import User
from app.schemas.common import ApiResponse, PageResponse
from app.schemas.outbox import OutboxBulkRetryResponse, OutboxDeliveryResponse
from app.services.outbox.admin import OutboxAdminService

RETRY_MESSAGE = "전달을 다시 처리하도록 바꿨습니다."

router = APIRouter(
    prefix="/admin/outbox",
    tags=["관리자"],
    dependencies=[Depends(require_admin)],
    responses=error_responses(AppError.INVALID_TOKEN, AppError.FORBIDDEN),
)


@router.get(
    "/deliveries",
    response_model=ApiResponse[PageResponse[OutboxDeliveryResponse]],
    status_code=status.HTTP_200_OK,
    summary="이벤트 전달 목록 조회 (관리자 전용)",
    description="전달 대상별 처리 기록을 조회합니다. 기본은 DEAD(끝내 실패한 전달)입니다. 기간은 끝난 시각(finishedAt) 기준입니다.",
    responses={200: success_response(ADMIN_OUTBOX_DELIVERY_PAGE_EXAMPLE), **error_responses(AppError.VALIDATION_ERROR)},
)
def list_outbox_deliveries(
    delivery_status: DeliveryStatus = Query(DeliveryStatus.DEAD, alias="status", description="전달 상태"),
    consumer: str | None = Query(None, max_length=50, description="전달 대상 이름 (예: chat.push)"),
    finished_from: datetime | None = Query(None, alias="from", description="끝난 시각 시작(포함)"),
    finished_to: datetime | None = Query(None, alias="to", description="끝난 시각 끝(미포함)"),
    page: int = Query(0, ge=0, description="페이지 번호 (0부터)"),
    size: int = Query(20, ge=1, le=100, description="페이지 크기"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageResponse[OutboxDeliveryResponse]]:
    data = OutboxAdminService.list_deliveries(
        db,
        delivery_status,
        consumer,
        to_utc_naive(finished_from) if finished_from else None,
        to_utc_naive(finished_to) if finished_to else None,
        page,
        size,
    )
    return ApiResponse(success=True, data=data, message=None)


@router.post(
    "/deliveries/retry",
    response_model=ApiResponse[OutboxBulkRetryResponse],
    status_code=status.HTTP_200_OK,
    summary="전달 대상의 DEAD 전달 일괄 재처리 (관리자 전용)",
    description="전달 대상(consumer)의 DEAD 전달을 모두 다시 처리하도록 바꿉니다. 재처리도 유효 시간이 지났으면 건너뜁니다.",
    responses={200: success_response(ADMIN_OUTBOX_BULK_RETRY_EXAMPLE), **error_responses(AppError.VALIDATION_ERROR)},
)
def retry_consumer_deliveries(
    consumer: str = Query(..., min_length=1, max_length=50, description="전달 대상 이름"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ApiResponse[OutboxBulkRetryResponse]:
    data = OutboxAdminService.retry_consumer(db, consumer, current_admin.id)
    return ApiResponse(success=True, data=data, message=RETRY_MESSAGE)


@router.post(
    "/deliveries/{delivery_id}/retry",
    response_model=ApiResponse[OutboxDeliveryResponse],
    status_code=status.HTTP_200_OK,
    summary="DEAD 전달 재처리 (관리자 전용)",
    description="DEAD 전달 하나를 다시 처리하도록 바꿉니다. 재시도 횟수를 새로 세고 재처리 횟수와 요청한 관리자를 남깁니다. DEAD가 아니면 409입니다.",
    responses={
        200: success_response(ADMIN_OUTBOX_RETRY_EXAMPLE),
        **error_responses(
            AppError.VALIDATION_ERROR,
            AppError.OUTBOX_DELIVERY_NOT_FOUND,
            AppError.OUTBOX_DELIVERY_NOT_RETRYABLE,
        ),
    },
)
def retry_delivery(
    delivery_id: int = Path(..., gt=0, description="전달 기록 ID"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ApiResponse[OutboxDeliveryResponse]:
    data = OutboxAdminService.retry_delivery(db, delivery_id, current_admin.id)
    return ApiResponse(success=True, data=data, message=RETRY_MESSAGE)
