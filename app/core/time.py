"""Time helpers shared by ORM models and services."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow_naive() -> datetime:
    """Return a UTC timestamp suitable for MySQL DATETIME columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive(value: datetime) -> datetime:
    """시간대가 있으면 UTC로 바꾸고, MySQL DATETIME 비교용으로 시간대 정보를 뗀다."""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value
