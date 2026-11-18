"""DEAD 전달 조회와 수동 재처리 (OUTBOX-REQ-006)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.errors import AppError, api_error
from app.models.outbox import DeliveryStatus, EventDelivery, OutboxEvent
from app.schemas.common import PageResponse
from app.schemas.outbox import OutboxBulkRetryResponse, OutboxDeliveryResponse

#: DEAD → PENDING 전이 값. 재시도 횟수를 새로 세고 알림 기록을 지운다.
_RETRY_VALUES = {
    "status": DeliveryStatus.PENDING,
    "attempts": 0,
    "next_attempt_at": None,
    "locked_until": None,
    "finished_at": None,
    "dead_alerted_at": None,
}


class OutboxAdminService:
    @staticmethod
    def list_deliveries(
        db: Session,
        status: DeliveryStatus,
        consumer: str | None,
        finished_from: datetime | None,
        finished_to: datetime | None,
        page: int,
        size: int,
    ) -> PageResponse[OutboxDeliveryResponse]:
        query = (
            db.query(EventDelivery, OutboxEvent)
            .join(OutboxEvent, OutboxEvent.event_id == EventDelivery.event_id)
            .filter(EventDelivery.status == status)
        )
        if consumer:
            query = query.filter(EventDelivery.consumer == consumer)
        if finished_from is not None:
            query = query.filter(EventDelivery.finished_at >= finished_from)
        if finished_to is not None:
            query = query.filter(EventDelivery.finished_at < finished_to)
        total = query.count()
        rows = query.order_by(EventDelivery.id.desc()).offset(page * size).limit(size).all()
        return PageResponse.of(
            content=[_to_response(delivery, event) for delivery, event in rows],
            page_number=page,
            page_size=size,
            total_elements=total,
        )

    @staticmethod
    def retry_delivery(db: Session, delivery_id: int, admin_id: str) -> OutboxDeliveryResponse:
        """DEAD 전달 하나를 다시 처리하도록 바꾼다. DEAD가 아니면 409.

        조건부 UPDATE 한 문장으로 바꾸므로 같은 전달에 요청이 동시에 와도 한 번만 바뀐다.
        """
        if db.get(EventDelivery, delivery_id) is None:
            raise api_error(AppError.OUTBOX_DELIVERY_NOT_FOUND)
        result = db.execute(
            update(EventDelivery)
            .where(EventDelivery.id == delivery_id, EventDelivery.status == DeliveryStatus.DEAD)
            .values(
                **_RETRY_VALUES,
                manual_retry_count=EventDelivery.manual_retry_count + 1,
                last_manual_retry_by=admin_id,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:
            db.rollback()
            raise api_error(AppError.OUTBOX_DELIVERY_NOT_RETRYABLE)
        db.commit()
        delivery = db.get(EventDelivery, delivery_id)
        db.refresh(delivery)
        event = db.query(OutboxEvent).filter(OutboxEvent.event_id == delivery.event_id).one()
        return _to_response(delivery, event)

    @staticmethod
    def retry_consumer(db: Session, consumer: str, admin_id: str) -> OutboxBulkRetryResponse:
        """전달 대상의 DEAD 전달을 모두 다시 처리하도록 바꾼다."""
        result = db.execute(
            update(EventDelivery)
            .where(EventDelivery.consumer == consumer, EventDelivery.status == DeliveryStatus.DEAD)
            .values(
                **_RETRY_VALUES,
                manual_retry_count=EventDelivery.manual_retry_count + 1,
                last_manual_retry_by=admin_id,
            )
            .execution_options(synchronize_session=False)
        )
        db.commit()
        return OutboxBulkRetryResponse(consumer=consumer, retried_count=result.rowcount)


def _to_response(delivery: EventDelivery, event: OutboxEvent) -> OutboxDeliveryResponse:
    return OutboxDeliveryResponse(
        id=delivery.id,
        event_id=delivery.event_id,
        event_type=event.event_type,
        aggregate_type=event.aggregate_type,
        aggregate_id=event.aggregate_id,
        consumer=delivery.consumer,
        status=delivery.status,
        attempts=delivery.attempts,
        last_error=delivery.last_error,
        skip_reason=delivery.skip_reason,
        manual_retry_count=delivery.manual_retry_count,
        occurred_at=event.occurred_at,
        next_attempt_at=delivery.next_attempt_at,
        finished_at=delivery.finished_at,
    )
