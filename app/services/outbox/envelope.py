"""이벤트 봉투 (OUTBOX-REQ-008). Kafka 메시지 형식과 같게 둔다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    schema_version: int
    occurred_at: datetime
    payload: dict[str, Any]

    @classmethod
    def from_event(cls, event) -> "EventEnvelope":
        return cls(
            event_id=event.event_id,
            event_type=event.event_type,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            schema_version=event.schema_version,
            occurred_at=event.occurred_at,
            payload=dict(event.payload or {}),
        )

    @property
    def key(self) -> str:
        """순서 키. Kafka 파티션 키로 쓴다."""
        return self.aggregate_id

    def to_message(self) -> dict[str, Any]:
        return {
            "eventId": self.event_id,
            "eventType": self.event_type,
            "aggregateType": self.aggregate_type,
            "aggregateId": self.aggregate_id,
            "schemaVersion": self.schema_version,
            "occurredAt": self.occurred_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "payload": self.payload,
        }
