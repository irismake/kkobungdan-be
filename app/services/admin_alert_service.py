"""관리자 운영 알림 발송. Slack Incoming Webhook으로 보낸다.

앱 사용자 알림(FCM)과 달리 수신자가 관리자이고, `notifications` 테이블에 남기지 않는다.
처리해야 할 일의 정본은 관리자 웹 목록(분쟁 PENDING, 미션 COMPLETED)이고 이 메시지는
그 목록을 보라는 재촉이므로, 한 건 유실돼도 일이 사라지지 않는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

#: Slack 응답을 기다리는 시간. 알림 하나 때문에 background task를 오래 붙잡지 않는다.
_TIMEOUT_SECONDS = 5.0
#: 일시적인 네트워크 오류를 흡수할 만큼만 재시도한다. 영속 큐가 아니므로 여기서 끝난다.
_MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class AdminAlert:
    """관리자에게 보낼 알림 한 건."""

    headline: str
    lines: list[str] = field(default_factory=list)
    link_label: str | None = None
    link_path: str | None = None

    def to_text(self) -> str:
        """Slack `text` 필드에 넣을 본문을 만든다."""
        parts = [self.headline, *self.lines]
        link = self._link()
        if link is not None:
            parts.append(link)
        return "\n".join(parts)

    def _link(self) -> str | None:
        """관리자 웹 주소가 설정돼 있을 때만 링크 줄을 만든다."""
        base = (settings.admin_web_base_url or "").rstrip("/")
        if not base or not self.link_path:
            return None
        return f"<{base}/{self.link_path.lstrip('/')}|{self.link_label or '관리자 웹에서 열기'}>"


class AdminAlertSender(Protocol):
    def send(self, alert: AdminAlert) -> None:
        """관리자 알림 한 건을 보낸다. 실패해도 예외를 밖으로 내보내지 않는다."""


class SlackAdminAlertSender:
    """Slack Incoming Webhook 발송기.

    webhook URL이 없으면 조용히 아무것도 하지 않는다. 알림은 운영 편의 기능이라
    미설정이 서비스 흐름을 막아서는 안 된다.
    """

    def __init__(self, webhook_url: str | None, client: httpx.Client | None = None) -> None:
        self.webhook_url = webhook_url
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def send(self, alert: AdminAlert) -> None:
        if not self.enabled:
            return

        payload = {"text": alert.to_text()}
        last_error: Exception | None = None

        for _ in range(_MAX_ATTEMPTS):
            try:
                response = self._post(payload)
            except Exception as error:  # noqa: BLE001 - 알림 실패가 API 응답을 깨뜨리면 안 된다
                last_error = error
                continue

            if response.status_code < 400:
                return
            last_error = RuntimeError(f"status={response.status_code} body={response.text[:200]}")
            # 4xx는 webhook URL이나 payload가 잘못된 것이라 재시도해도 같다.
            if response.status_code < 500:
                break

        logger.error("관리자 Slack 알림 발송에 실패했습니다: %s | %s", alert.headline, last_error)

    def _post(self, payload: dict) -> httpx.Response:
        if self._client is not None:
            return self._client.post(self.webhook_url, json=payload, timeout=_TIMEOUT_SECONDS)
        with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
            return client.post(self.webhook_url, json=payload)


def send_admin_alerts(alerts: list[AdminAlert]) -> None:
    """BackgroundTask 진입점. 한 건이 실패해도 나머지를 계속 보낸다."""
    sender = get_admin_alert_sender()
    for alert in alerts:
        sender.send(alert)


def get_admin_alert_sender() -> AdminAlertSender:
    return SlackAdminAlertSender(webhook_url=settings.admin_alert_slack_webhook_url)


__all__ = [
    "AdminAlert",
    "AdminAlertSender",
    "SlackAdminAlertSender",
    "get_admin_alert_sender",
    "send_admin_alerts",
]
