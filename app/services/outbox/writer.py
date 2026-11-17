"""이벤트 기록 (OUTBOX-REQ-001). 호출한 세션에 1행을 추가만 하고 커밋하지 않는다."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.time import utcnow_naive
from app.models.outbox import OutboxEvent

#: 이 세션에서 이벤트를 기록했는지 표시. 커밋 직후 발행 작업을 깨우는 데 쓴다(wakeup.py).
RECORDED_FLAG = "outbox_recorded"


def record_event(
    db: Session,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str | int,
    payload: dict[str, Any],
    schema_version: int = 1,
    occurred_at: datetime | None = None,
) -> OutboxEvent:
    event = OutboxEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id),
        schema_version=schema_version,
        payload=payload,
        occurred_at=occurred_at or utcnow_naive(),
        publish_attempts=0,
    )
    db.add(event)
    db.info[RECORDED_FLAG] = True
    return event
