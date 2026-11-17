"""Outbox 주기 작업과 커밋 직후 깨우기 (docs/design-docs/outbox.md 구성).

- 처리 작업(10초마다, 커밋 직후에도 바로 1번): 미발행 이벤트 발행 → 처리할 전달(재시도 시각이 된 것 포함) 처리 → 발행 지연 점검
- 정리 작업(매일 04:00): 끝난 지 7일 지난 이벤트 삭제
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.time import utcnow_naive
from app.services.admin_alert_service import get_admin_alert_sender
from app.services.outbox.cleanup import cleanup_finished_events
from app.services.outbox.consumers import ConsumerRegistry, consumer_registry
from app.services.outbox.delivery import process_due_deliveries
from app.services.outbox.monitor import PublishDelayMonitor
from app.services.outbox.publisher import EventPublisher, InProcessEventPublisher
from app.services.outbox.relay import oldest_unpublished_at, publish_pending
from app.services.outbox.writer import RECORDED_FLAG

logger = logging.getLogger(__name__)

CYCLE_INTERVAL_SECONDS = 10
CLEANUP_HOUR = 4

_wake_callback: Callable[[], None] | None = None


@event.listens_for(Session, "after_commit")
def _wake_after_commit(session: Session) -> None:
    if session.info.pop(RECORDED_FLAG, False):
        try:
            wake_after_commit()
        except Exception:  # noqa: BLE001 - 깨우기 실패는 주기 작업이 메운다
            logger.exception("outbox 발행 깨우기 실패")


@event.listens_for(Session, "after_rollback")
def _clear_after_rollback(session: Session) -> None:
    session.info.pop(RECORDED_FLAG, None)


def wake_after_commit() -> None:
    """이벤트가 기록된 트랜잭션이 커밋되면 호출된다. 워커가 없으면(테스트 등) 아무것도 하지 않는다."""
    if _wake_callback is not None:
        _wake_callback()


def register_outbox_jobs(scheduler, worker: "OutboxWorker") -> None:
    """주기 작업 두 개를 등록하고 커밋 직후 깨우기를 연결한다.

    - `outbox_cycle`: 10초마다 처리 작업
    - `outbox_cleanup`: 매일 04:00 정리
    - 커밋 직후에는 `outbox_cycle_now`로 처리 작업을 바로 한 번 실행한다. 정상 채팅은 10초를 기다리지 않는다.
    """
    scheduler.add_job(worker.run_cycle, "interval", seconds=CYCLE_INTERVAL_SECONDS, id="outbox_cycle", replace_existing=True)
    scheduler.add_job(worker.cleanup, "cron", hour=CLEANUP_HOUR, minute=0, id="outbox_cleanup", replace_existing=True)
    set_wake_callback(lambda: scheduler.add_job(worker.run_cycle, id="outbox_cycle_now", replace_existing=True))


def set_wake_callback(callback: Callable[[], None] | None) -> None:
    """커밋 직후 호출할 함수를 등록한다. 워커가 켜질 때 등록하고, 테스트처럼 워커가 없으면 None이다."""
    global _wake_callback
    _wake_callback = callback


class OutboxWorker:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        registry: ConsumerRegistry = consumer_registry,
        publisher: EventPublisher | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry
        self._publisher = publisher or InProcessEventPublisher(registry)
        self._monitor = PublishDelayMonitor(get_admin_alert_sender())
        self._cycle_lock = threading.Lock()

    def run_cycle(self) -> None:
        """처리 작업 한 번: 미발행 이벤트를 모두 발행하고, 처리할 전달을 처리하고, 발행 지연을 점검한다.

        커밋 직후 깨우기와 10초 주기가 겹쳐 불려도 한 번에 하나만 돈다(나머지는 바로 끝난다).
        """
        if not self._cycle_lock.acquire(blocking=False):
            return
        try:
            self._with_session(self._publish_all)
            self._with_session(
                lambda db: process_due_deliveries(db, self._registry, utcnow_naive(), get_admin_alert_sender())
            )
            self._with_session(lambda db: self._monitor.check(oldest_unpublished_at(db), utcnow_naive()))
        finally:
            self._cycle_lock.release()

    def cleanup(self) -> None:
        deleted = self._with_session(lambda db: cleanup_finished_events(db, utcnow_naive()))
        if deleted:
            logger.info("outbox 정리: 이벤트 %s건 삭제", deleted)

    def _publish_all(self, db: Session) -> None:
        while publish_pending(db, self._publisher, utcnow_naive()) > 0:
            pass

    def _with_session(self, work):
        db = self._session_factory()
        try:
            return work(db)
        except Exception:  # noqa: BLE001 - 주기 작업은 다음 주기에 다시 돈다
            db.rollback()
            logger.exception("outbox 작업 실패")
            return None
        finally:
            db.close()
