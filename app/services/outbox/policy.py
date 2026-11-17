"""재시도 정책 (OUTBOX-REQ-002·005). 대상별 값은 product-specs/event-delivery.md가 정본이다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

#: 발행 실패 간격. 마지막 값(10분)을 계속 반복하고 포기하지 않는다.
PUBLISH_BACKOFF: tuple[timedelta, ...] = (
    timedelta(seconds=5),
    timedelta(seconds=30),
    timedelta(minutes=2),
    timedelta(minutes=10),
)

#: 처리 중(PROCESSING) 임대 시간. 처리하던 작업이 멈추면 이 시간 뒤 다시 집는다.
DELIVERY_LEASE = timedelta(minutes=5)


@dataclass(frozen=True)
class RetryPolicy:
    """전달 대상의 재시도 정책.

    max_retries: 첫 시도 뒤 다시 시도하는 최대 횟수. 넘기면 DEAD.
    backoff: n번째 재시도 간격. 길이를 넘으면 마지막 값을 반복한다.
    expires_after: 이벤트 발생 후 유효 시간. 지나면 처리하지 않고 SKIPPED. None이면 무제한.
    """

    max_retries: int
    backoff: tuple[timedelta, ...]
    expires_after: timedelta | None = None

    def delay_for(self, retry_number: int) -> timedelta:
        index = min(max(retry_number, 1), len(self.backoff)) - 1
        return self.backoff[index]


DEFAULT_RETRY_POLICY = RetryPolicy(
    max_retries=5,
    backoff=(timedelta(seconds=5), timedelta(seconds=30), timedelta(minutes=2), timedelta(minutes=10)),
)


def publish_retry_delay(attempts: int) -> timedelta:
    """발행에 `attempts`번 실패한 뒤 다음 시도까지 기다릴 시간."""
    index = min(max(attempts, 1), len(PUBLISH_BACKOFF)) - 1
    return PUBLISH_BACKOFF[index]
