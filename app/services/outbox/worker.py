"""Outbox 주기 작업과 커밋 직후 깨우기 (docs/design-docs/outbox.md 구성).

- 발행: 커밋 직후 깨움 + 2초마다
- 전달 처리(재시도 포함): 발행 직후 + 10초마다
- 발행 지연 점검: 1분마다
- 정리: 하루 1번
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

_wake_callback: Callable[[], None] | None = None


@event.listens_for(Session, "after_commit")
def _wake_after_commit(session: Session) -> None:
    if session.info.pop(RECORDED_FLAG, False) and _wake_callback is not None:
        try:
            _wake_callback()
        except Exception:  # noqa: BLE001 - 깨우기 실패는 주기 작업이 메운다
            logger.exception("outbox 발행 깨우기 실패")


@event.listens_for(Session, "after_rollback")
def _clear_after_rollback(session: Session) -> None:
    session.info.pop(RECORDED_FLAG, None)


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
        """미발행 이벤트를 모두 발행하고 처리할 전달을 처리한다. 겹쳐 불려도 한 번에 하나만 돈다."""
        if not self._cycle_lock.acquire(blocking=False):
            return
        try:
            self._with_session(self._publish_all)
            self.run_deliveries()
        finally:
            self._cycle_lock.release()

    def run_deliveries(self) -> None:
        self._with_session(
            lambda db: process_due_deliveries(db, self._registry, utcnow_naive(), get_admin_alert_sender())
        )

    def check_publish_delay(self) -> None:
        self._with_session(lambda db: self._monitor.check(oldest_unpublished_at(db), utcnow_naive()))

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
