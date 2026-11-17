"""발행 작업 (OUTBOX-REQ-002). 미발행 이벤트를 기록 순서대로 발행자에 넘긴다."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.outbox import OutboxEvent
from app.services.outbox.envelope import EventEnvelope
from app.services.outbox.policy import publish_retry_delay
from app.services.outbox.publisher import EventPublisher

logger = logging.getLogger(__name__)

PUBLISH_BATCH_SIZE = 100


def plan_publish(events: Iterable, now: datetime) -> list:
    """기록 순서(id)대로 발행할 이벤트를 고른다.

    같은 대상(aggregate)의 앞선 이벤트가 발행 실패로 다음 시도를 기다리면, 그 대상의 뒤 이벤트도
    고르지 않는다. 순서가 뒤바뀌지 않게 하기 위해서다. 다른 대상은 막지 않는다.
    """
    blocked: set[tuple[str, str]] = set()
    planned = []
    for event in sorted(events, key=lambda item: item.id):
        key = (event.aggregate_type, event.aggregate_id)
        if key in blocked:
            continue
        if event.next_publish_at is not None and event.next_publish_at > now:
            blocked.add(key)
            continue
        planned.append(event)
    return planned


def publish_pending(db: Session, publisher: EventPublisher, now: datetime, limit: int = PUBLISH_BATCH_SIZE) -> int:
    """미발행 이벤트를 집어 발행하고, 발행한 개수를 돌려준다.

    `FOR UPDATE SKIP LOCKED`로 집으므로 발행 작업이 동시에 돌아도 한 이벤트는 한 작업만 집는다.
    다른 작업이 앞선 이벤트를 잡고 있는 대상은 이번에 건너뛴다(순서 보장).
    """
    candidates = (
        db.query(OutboxEvent)
        .filter(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
        .all()
    )
    if not candidates:
        db.commit()
        return 0

    candidate_ids = {event.id for event in candidates}
    keys = {(event.aggregate_type, event.aggregate_id) for event in candidates}
    first_unpublished = dict(
        ((row[0], row[1]), row[2])
        for row in db.query(OutboxEvent.aggregate_type, OutboxEvent.aggregate_id, func.min(OutboxEvent.id))
        .filter(OutboxEvent.published_at.is_(None))
        .group_by(OutboxEvent.aggregate_type, OutboxEvent.aggregate_id)
        .all()
        if (row[0], row[1]) in keys
    )
    # 앞선 이벤트를 다른 작업이 잡고 있는 대상은 이번 배치에서 뺀다.
    held_elsewhere = {key for key, first_id in first_unpublished.items() if first_id not in candidate_ids}
    candidates = [event for event in candidates if (event.aggregate_type, event.aggregate_id) not in held_elsewhere]

    published = 0
    failed_keys: set[tuple[str, str]] = set()
    for event in plan_publish(candidates, now):
        key = (event.aggregate_type, event.aggregate_id)
        if key in failed_keys:
            continue
        try:
            publisher.publish(EventEnvelope.from_event(event), db)
        except Exception as exc:  # noqa: BLE001 - 발행 실패는 기록하고 다시 시도한다
            event.publish_attempts = (event.publish_attempts or 0) + 1
            event.next_publish_at = now + publish_retry_delay(event.publish_attempts)
            event.last_publish_error = f"{type(exc).__name__}: {exc}"[:500]
            failed_keys.add(key)
            logger.warning("outbox 발행 실패 event_id=%s attempts=%s: %s", event.event_id, event.publish_attempts, exc)
            continue
        event.publish_attempts = (event.publish_attempts or 0) + 1
        event.published_at = now
        event.next_publish_at = None
        event.last_publish_error = None
        published += 1
    db.commit()
    return published


def oldest_unpublished_at(db: Session) -> datetime | None:
    """가장 오래된 미발행 이벤트의 발생 시각. 발행 지연 점검에 쓴다."""
    return (
        db.query(OutboxEvent.occurred_at)
        .filter(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.id)
        .limit(1)
        .scalar()
    )
