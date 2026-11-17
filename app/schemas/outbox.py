"""Outbox admin schemas (OUTBOX-REQ-006)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.outbox import DeliveryStatus


class OutboxDeliveryResponse(BaseModel):
    """전달 대상별 처리 기록 1건."""

    id: int
    event_id: str = Field(..., serialization_alias="eventId")
    event_type: str = Field(..., serialization_alias="eventType")
    aggregate_type: str = Field(..., serialization_alias="aggregateType")
    aggregate_id: str = Field(..., serialization_alias="aggregateId")
    consumer: str = Field(..., description="전달 대상 이름 (예: chat.push)")
    status: DeliveryStatus
    attempts: int = Field(..., description="이번 회차의 시도 횟수. 수동 재처리 때 0으로 되돌린다")
    last_error: str | None = Field(None, serialization_alias="lastError")
    skip_reason: str | None = Field(None, serialization_alias="skipReason")
    manual_retry_count: int = Field(..., serialization_alias="manualRetryCount")
    occurred_at: datetime = Field(..., serialization_alias="occurredAt")
    next_attempt_at: datetime | None = Field(None, serialization_alias="nextAttemptAt")
    finished_at: datetime | None = Field(None, serialization_alias="finishedAt")

    model_config = ConfigDict(populate_by_name=True)


class OutboxBulkRetryResponse(BaseModel):
    consumer: str
    retried_count: int = Field(..., serialization_alias="retriedCount", description="다시 처리하도록 바꾼 DEAD 전달 수")

    model_config = ConfigDict(populate_by_name=True)
