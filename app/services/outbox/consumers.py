"""전달 대상(consumer) 인터페이스와 등록 (OUTBOX-REQ-004·005)."""

from __future__ import annotations

from typing import Protocol

from app.services.outbox.envelope import EventEnvelope
from app.services.outbox.policy import RetryPolicy


class SkipDelivery(Exception):
    """처리할 필요가 없어 SKIPPED로 끝낸다(예: 받을 사람이 없음). 실패가 아니다."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class EventConsumer(Protocol):
    """이벤트를 받아 실제 일을 하는 곳. 같은 이벤트를 두 번 받아도 결과가 같아야 한다(멱등)."""

    name: str
    event_types: frozenset[str]
    retry_policy: RetryPolicy

    def handle(self, envelope: EventEnvelope) -> None: ...


class ConsumerRegistry:
    """어떤 이벤트 유형을 어떤 전달 대상이 받는지 등록한다."""

    def __init__(self) -> None:
        self._consumers: dict[str, EventConsumer] = {}

    def register(self, consumer: EventConsumer) -> None:
        existing = self._consumers.get(consumer.name)
        if existing is not None and existing is not consumer:
            raise ValueError(f"이미 등록된 전달 대상 이름이다: {consumer.name}")
        self._consumers[consumer.name] = consumer

    def get(self, name: str) -> EventConsumer | None:
        return self._consumers.get(name)

    def consumers_for(self, event_type: str) -> list[EventConsumer]:
        return [consumer for consumer in self._consumers.values() if event_type in consumer.event_types]


#: 앱 전체에서 쓰는 등록부. 도메인(채팅 등)이 시작할 때 전달 대상을 등록한다.
consumer_registry = ConsumerRegistry()
