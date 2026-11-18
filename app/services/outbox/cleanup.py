"""정리 배치 (OUTBOX-REQ-007). 끝난 이벤트만 7일 뒤 지운다."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.outbox import DeliveryStatus, EventDelivery, OutboxEvent

RETENTION = timedelta(days=7)
CLEANUP_BATCH_SIZE = 1000

_DONE = (DeliveryStatus.SUCCEEDED, DeliveryStatus.SKIPPED)


def cleanup_finished_events(
    db: Session,
    now: datetime,
    retention: timedelta = RETENTION,
    batch_size: int = CLEANUP_BATCH_SIZE,
) -> int:
    """발행됐고 모든 전달이 SUCCEEDED·SKIPPED이며 마지막으로 끝난 지 `retention`이 지난 이벤트를 지운다.

    DEAD·FAILED·PENDING·PROCESSING 전달이 하나라도 있거나 미발행인 이벤트는 지우지 않는다.
    삭제한 이벤트 수를 돌려준다.
    """
    cutoff = now - retention
    delivery_summary = (
        db.query(
            EventDelivery.event_id.label("event_id"),
            func.max(EventDelivery.finished_at).label("last_finished_at"),
            func.sum(case((EventDelivery.status.in_(_DONE), 0), else_=1)).label("open_count"),
        )
        .group_by(EventDelivery.event_id)
        .subquery()
    )
    deleted_total = 0
    while True:
        event_ids = [
            row[0]
            for row in db.query(OutboxEvent.event_id)
            .outerjoin(delivery_summary, delivery_summary.c.event_id == OutboxEvent.event_id)
            .filter(
                OutboxEvent.published_at.isnot(None),
                func.coalesce(delivery_summary.c.open_count, 0) == 0,
                func.coalesce(delivery_summary.c.last_finished_at, OutboxEvent.published_at) < cutoff,
            )
            .order_by(OutboxEvent.id)
            .limit(batch_size)
            .all()
        ]
        if not event_ids:
            break
        db.query(EventDelivery).filter(EventDelivery.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(OutboxEvent).filter(OutboxEvent.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.commit()
        deleted_total += len(event_ids)
        if len(event_ids) < batch_size:
            break
    return deleted_total


__all__ = ["cleanup_finished_events", "RETENTION"]


