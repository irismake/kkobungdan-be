"""발행 지연 모니터링 (OUTBOX-REQ-003)."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.services.admin_alert_service import AdminAlert

PUBLISH_DELAY_THRESHOLD = timedelta(minutes=5)
PUBLISH_DELAY_REPEAT = timedelta(minutes=30)


class PublishDelayMonitor:
    """가장 오래된 미발행 이벤트가 5분을 넘으면 알린다. 지연이 이어지면 30분에 한 번, 풀리면 해소 알림 1번.

    상태는 프로세스 메모리에 둔다. 재시작하면 같은 지연을 한 번 더 알릴 수 있다.
    """

    def __init__(
        self,
        alert_sender,
        threshold: timedelta = PUBLISH_DELAY_THRESHOLD,
        repeat: timedelta = PUBLISH_DELAY_REPEAT,
    ) -> None:
        self._alerts = alert_sender
        self._threshold = threshold
        self._repeat = repeat
        self._delayed = False
        self._last_alert_at: datetime | None = None

    def check(self, oldest_unpublished_at: datetime | None, now: datetime) -> None:
        delayed = oldest_unpublished_at is not None and now - oldest_unpublished_at > self._threshold
        if delayed:
            if self._last_alert_at is None or now - self._last_alert_at >= self._repeat:
                minutes = int((now - oldest_unpublished_at).total_seconds() // 60)
                self._alerts.send(
                    AdminAlert(
                        headline="⏳ 이벤트 발행이 밀리고 있어요",
                        lines=[f"가장 오래된 미발행 이벤트가 {minutes}분째 발행되지 않았어요.", "발행자(또는 Kafka) 상태를 확인해주세요."],
                    )
                )
                self._last_alert_at = now
            self._delayed = True
            return
        if self._delayed:
            self._alerts.send(AdminAlert(headline="✅ 이벤트 발행 지연이 해소됐어요"))
        self._delayed = False
        self._last_alert_at = None
