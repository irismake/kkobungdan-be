"""전달 처리 (OUTBOX-REQ-004·005·006).

- `execute_delivery`: 전달 하나를 실행하고 결과를 정하는 순수 규칙 (DB를 모른다)
- `claim_due_deliveries`: 처리할 전달을 PROCESSING(5분 임대)으로 집는다
- `process_due_deliveries`: 집은 전달을 처리하고 결과를 기록한다
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.outbox import FINISHED_DELIVERY_STATUSES, DeliveryStatus, EventDelivery, OutboxEvent
from app.services.admin_alert_service import AdminAlert
from app.services.outbox.consumers import ConsumerRegistry, EventConsumer, SkipDelivery
from app.services.outbox.envelope import EventEnvelope
from app.services.outbox.policy import DELIVERY_LEASE

logger = logging.getLogger(__name__)

CLAIM_BATCH_SIZE = 50


@dataclass(frozen=True)
class DeliveryOutcome:
    status: DeliveryStatus
    next_attempt_at: datetime | None = None
    error: str | None = None
    skip_reason: str | None = None


def execute_delivery(consumer: EventConsumer, envelope: EventEnvelope, attempts: int, now: datetime) -> DeliveryOutcome:
    """전달 하나를 실행한다. `attempts`는 이번 회차에서 이미 실패한 횟수다(수동 재처리 때 0).

    유효 시간이 지났으면 전달 대상을 부르지 않고 SKIPPED. 실패하면 정책 간격으로 FAILED,
    최대 재시도를 넘기면 DEAD.
    """
    policy = consumer.retry_policy
    if policy.expires_after is not None and now >= envelope.occurred_at + policy.expires_after:
        return DeliveryOutcome(DeliveryStatus.SKIPPED, skip_reason="expired")
    try:
        consumer.handle(envelope)
    except SkipDelivery as skip:
        return DeliveryOutcome(DeliveryStatus.SKIPPED, skip_reason=skip.reason[:50])
    except Exception as exc:  # noqa: BLE001 - 전달 실패는 결과로 기록한다
        error = f"{type(exc).__name__}: {exc}"[:500]
        failures = attempts + 1
        if failures > policy.max_retries:
            return DeliveryOutcome(DeliveryStatus.DEAD, error=error)
        return DeliveryOutcome(DeliveryStatus.FAILED, next_attempt_at=now + policy.delay_for(failures), error=error)
    return DeliveryOutcome(DeliveryStatus.SUCCEEDED)


def is_claimable(delivery, now: datetime) -> bool:
    """지금 처리해도 되는 전달인가. 끝난 전달(SUCCEEDED·SKIPPED·DEAD)은 다시 집지 않는다."""
    if delivery.status == DeliveryStatus.PENDING:
        return True
    if delivery.status == DeliveryStatus.FAILED:
        return delivery.next_attempt_at is None or delivery.next_attempt_at <= now
    if delivery.status == DeliveryStatus.PROCESSING:
        return delivery.locked_until is not None and delivery.locked_until <= now
    return False


def alert_dead_delivery(delivery, envelope: EventEnvelope, alert_sender, now: datetime) -> None:
    """DEAD가 된 전달을 오류 로그로 남기고, 아직 알리지 않았으면 관리자에게 한 번 알린다."""
    logger.error(
        "outbox 전달 DEAD consumer=%s event_type=%s event_id=%s aggregate=%s:%s attempts=%s error=%s",
        delivery.consumer,
        envelope.event_type,
        envelope.event_id,
        envelope.aggregate_type,
        envelope.aggregate_id,
        delivery.attempts,
        delivery.last_error,
    )
    if delivery.dead_alerted_at is not None:
        return
    alert_sender.send(
        AdminAlert(
            headline="🚨 이벤트 전달이 끝내 실패했어요 (DEAD)",
            lines=[
                f"전달 대상: {delivery.consumer}",
                f"이벤트: {envelope.event_type} · {envelope.aggregate_type} #{envelope.aggregate_id}",
                f"시도: {delivery.attempts}회",
                f"오류: {delivery.last_error}",
            ],
            link_label="DEAD 전달 목록에서 다시 처리",
            link_path="outbox?status=DEAD",
        )
    )
    delivery.dead_alerted_at = now


def _due_filter(now: datetime):
    return or_(
        EventDelivery.status == DeliveryStatus.PENDING,
        and_(
            EventDelivery.status == DeliveryStatus.FAILED,
            or_(EventDelivery.next_attempt_at.is_(None), EventDelivery.next_attempt_at <= now),
        ),
        and_(EventDelivery.status == DeliveryStatus.PROCESSING, EventDelivery.locked_until <= now),
    )


def claim_due_deliveries(db: Session, now: datetime, limit: int = CLAIM_BATCH_SIZE) -> list[EventDelivery]:
    """처리할 전달을 집어 PROCESSING(임대 5분)으로 바꾸고 커밋한다.

    같은 전달 대상·같은 대상(aggregate)에 앞선 전달이 아직 끝나지 않았으면 뒤 전달은 집지 않는다.
    재시도 중에도 순서가 바뀌지 않게 하기 위해서다.
    """
    rows = (
        db.query(EventDelivery, OutboxEvent.id, OutboxEvent.aggregate_type, OutboxEvent.aggregate_id)
        .join(OutboxEvent, OutboxEvent.event_id == EventDelivery.event_id)
        .filter(_due_filter(now))
        .order_by(OutboxEvent.id, EventDelivery.id)
        .limit(limit)
        .with_for_update(skip_locked=True, of=EventDelivery)
        .all()
    )
    if not rows:
        db.commit()
        return []

    keys = {(delivery.consumer, aggregate_type, aggregate_id) for delivery, _, aggregate_type, aggregate_id in rows}
    first_open = {
        (row[0], row[1], row[2]): row[3]
        for row in db.query(EventDelivery.consumer, OutboxEvent.aggregate_type, OutboxEvent.aggregate_id, func.min(OutboxEvent.id))
        .join(OutboxEvent, OutboxEvent.event_id == EventDelivery.event_id)
        .filter(EventDelivery.status.notin_(list(FINISHED_DELIVERY_STATUSES)))
        .group_by(EventDelivery.consumer, OutboxEvent.aggregate_type, OutboxEvent.aggregate_id)
        .all()
        if (row[0], row[1], row[2]) in keys
    }

    claimed: list[EventDelivery] = []
    taken: set[tuple[str, str, str]] = set()
    for delivery, event_pk, aggregate_type, aggregate_id in rows:
        key = (delivery.consumer, aggregate_type, aggregate_id)
        if key in taken or first_open.get(key) != event_pk:
            continue
        taken.add(key)
        delivery.status = DeliveryStatus.PROCESSING
        delivery.locked_until = now + DELIVERY_LEASE
        claimed.append(delivery)
    db.commit()
    return claimed


def process_due_deliveries(db: Session, registry: ConsumerRegistry, now: datetime, alert_sender) -> int:
    """처리할 전달을 집어 실행하고 결과를 기록한다. 처리한 개수를 돌려준다."""
    processed = 0
    for delivery in claim_due_deliveries(db, now):
        event = db.query(OutboxEvent).filter(OutboxEvent.event_id == delivery.event_id).one()
        envelope = EventEnvelope.from_event(event)
        consumer = registry.get(delivery.consumer)
        if consumer is None:
            outcome = DeliveryOutcome(DeliveryStatus.DEAD, error=f"등록되지 않은 전달 대상: {delivery.consumer}")
        else:
            outcome = execute_delivery(consumer, envelope, delivery.attempts or 0, now)
        _apply(delivery, outcome, now)
        if outcome.status == DeliveryStatus.DEAD:
            alert_dead_delivery(delivery, envelope, alert_sender, now)
        db.commit()
        processed += 1
    return processed


def _apply(delivery: EventDelivery, outcome: DeliveryOutcome, now: datetime) -> None:
    delivery.status = outcome.status
    delivery.locked_until = None
    delivery.next_attempt_at = outcome.next_attempt_at
    if outcome.status in (DeliveryStatus.FAILED, DeliveryStatus.DEAD):
        delivery.attempts = (delivery.attempts or 0) + 1
        delivery.last_error = outcome.error
    if outcome.status == DeliveryStatus.SKIPPED:
        delivery.skip_reason = outcome.skip_reason
    if outcome.status in FINISHED_DELIVERY_STATUSES:
        delivery.finished_at = now
