"""발행자 (OUTBOX-REQ-002·008). 지금은 같은 프로세스, Kafka 도입 시 KafkaEventPublisher를 추가한다."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.models.outbox import DeliveryStatus, EventDelivery
from app.services.outbox.consumers import ConsumerRegistry
from app.services.outbox.envelope import EventEnvelope


class EventPublisher(Protocol):
    def publish(self, envelope: EventEnvelope, db: Session) -> None:
        """이벤트를 발행한다. 실패하면 예외를 던진다(relay가 다시 시도한다)."""


class InProcessEventPublisher:
    """받는 전달 대상마다 `event_deliveries`를 PENDING으로 만든다. 실제 처리는 전달 처리 단계가 한다.

    relay와 같은 트랜잭션에서 실행되므로 '발행 완료'와 '전달할 일 기록'이 함께 커밋된다.
    이미 있는 (event_id, consumer)는 다시 만들지 않는다.
    """

    def __init__(self, registry: ConsumerRegistry):
        self._registry = registry

    def publish(self, envelope: EventEnvelope, db: Session) -> None:
        consumers = self._registry.consumers_for(envelope.event_type)
        if not consumers:
            return
        existing = {
            row[0]
            for row in db.query(EventDelivery.consumer)
            .filter(EventDelivery.event_id == envelope.event_id)
            .all()
        }
        for consumer in consumers:
            if consumer.name in existing:
                continue
            db.add(
                EventDelivery(
                    event_id=envelope.event_id,
                    consumer=consumer.name,
                    status=DeliveryStatus.PENDING,
                    attempts=0,
                )
            )
