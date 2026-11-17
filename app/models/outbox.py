"""Transactional Outbox models (docs/design-docs/outbox.md 데이터 모델)."""

from __future__ import annotations

import enum

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, Integer, SmallInteger, String, UniqueConstraint

from app.core.database import Base
from app.core.time import utcnow_naive
from app.models.enum_type import enum_column


class DeliveryStatus(str, enum.Enum):
    """전달 대상 하나가 이벤트 하나를 처리한 상태."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    DEAD = "DEAD"


FINISHED_DELIVERY_STATUSES = frozenset({DeliveryStatus.SUCCEEDED, DeliveryStatus.SKIPPED, DeliveryStatus.DEAD})


class OutboxEvent(Base):
    """상태 변경과 같은 트랜잭션에 기록한 이벤트 1건."""

    __tablename__ = "outbox_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(String(36), nullable=False)
    event_type = Column(String(60), nullable=False)
    aggregate_type = Column(String(30), nullable=False)
    aggregate_id = Column(String(64), nullable=False)
    schema_version = Column(SmallInteger, nullable=False, default=1)
    payload = Column(JSON, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    publish_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    next_publish_at = Column(DateTime(timezone=True), nullable=True)
    last_publish_error = Column(String(500), nullable=True)

    __table_args__ = (
        UniqueConstraint("event_id", name="uk_outbox_events_event_id"),
        Index("idx_outbox_events_unpublished", "published_at", "next_publish_at", "id"),
        Index("idx_outbox_events_aggregate", "aggregate_type", "aggregate_id", "id"),
    )


class EventDelivery(Base):
    """전달 대상별 처리 기록. (event_id, consumer)가 중복 처리 방지 키다."""

    __tablename__ = "event_deliveries"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(String(36), nullable=False)
    consumer = Column(String(50), nullable=False)
    status = Column(
        enum_column(DeliveryStatus, 12, table="event_deliveries", column="status"),
        nullable=False,
        default=DeliveryStatus.PENDING,
    )
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String(500), nullable=True)
    skip_reason = Column(String(50), nullable=True)
    dead_alerted_at = Column(DateTime(timezone=True), nullable=True)
    manual_retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_manual_retry_by = Column(String(36), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive, onupdate=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("event_id", "consumer", name="uk_event_deliveries_event_consumer"),
        Index("idx_event_deliveries_status_next_attempt", "status", "next_attempt_at"),
        Index("idx_event_deliveries_status_locked", "status", "locked_until"),
        Index("idx_event_deliveries_consumer_status_finished", "consumer", "status", "finished_at"),
    )
