"""현재 DB 작업 단위에서 만들어진 관리자 알림을 커밋 이후까지 들고 가는 헬퍼.

`notification_outbox`와 같은 방식으로 세션에 적재한다. 다른 점은 알림을 DB 행으로 남기지
않는다는 것뿐이다. 리스너는 여기에 쌓기만 하고 실제 Slack POST는 커밋이 끝난 뒤
BackgroundTask에서 한다. 트랜잭션 안에서 외부 HTTP를 부르면 트랜잭션이 네트워크 지연만큼
길어지고, 뒤에 롤백된 트랜잭션에 대해서도 알림이 나가버린다.
"""
from __future__ import annotations

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.services.admin_alert_service import AdminAlert, send_admin_alerts

_SESSION_KEY = "admin_alerts"


def track_admin_alert(db: Session, alert: AdminAlert) -> None:
    db.info.setdefault(_SESSION_KEY, []).append(alert)


def pop_admin_alerts(db: Session) -> list[AdminAlert]:
    return db.info.pop(_SESSION_KEY, [])


def queue_admin_alerts(background_tasks: BackgroundTasks, db: Session) -> None:
    """커밋 이후 실행되도록 관리자 알림 발송을 예약한다."""
    alerts = pop_admin_alerts(db)
    if alerts:
        background_tasks.add_task(send_admin_alerts, alerts)


__all__ = ["pop_admin_alerts", "queue_admin_alerts", "track_admin_alert"]
