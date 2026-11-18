"""Outbox 단위 테스트 (DB 없이 순수 규칙 검증: 재시도·발행 순서·봉투·알림).

시나리오 정본: docs/domains/outbox/test-scenarios.md 의 OUTBOX-TS-*
설계: docs/design-docs/outbox.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

NOW = datetime(2026, 11, 17, 12, 0, 0)


@dataclass
class RecordingAlerts:
    sent: list = field(default_factory=list)

    def send(self, alert) -> None:
        self.sent.append(alert)


class FailingConsumer:
    name = "test.failing"
    event_types = frozenset({"test.happened"})

    def __init__(self, retry_policy):
        self.retry_policy = retry_policy
        self.calls = 0

    def handle(self, envelope) -> None:
        self.calls += 1
        raise RuntimeError("전달 실패")


def envelope(occurred_at: datetime = NOW, aggregate_id: str = "42"):
    from app.services.outbox.envelope import EventEnvelope

    return EventEnvelope(
        event_id="8f0c7d6e-0000-4000-8000-000000000001",
        event_type="test.happened",
        aggregate_type="test_aggregate",
        aggregate_id=aggregate_id,
        schema_version=1,
        occurred_at=occurred_at,
        payload={"value": 1},
    )


def pending_event(event_id: int, aggregate_id: str, next_publish_at: datetime | None = None):
    return SimpleNamespace(
        id=event_id,
        aggregate_type="test_aggregate",
        aggregate_id=aggregate_id,
        published_at=None,
        next_publish_at=next_publish_at,
    )


# ------------------------------------------------------------------ 발행 (OUTBOX-REQ-002)


@pytest.mark.scenario("OUTBOX-TS-003")
def test_publish_retry_backs_off_up_to_ten_minutes_and_never_gives_up() -> None:
    from app.services.outbox.policy import publish_retry_delay

    assert [publish_retry_delay(attempts) for attempts in (1, 2, 3, 4)] == [
        timedelta(seconds=5),
        timedelta(seconds=30),
        timedelta(minutes=2),
        timedelta(minutes=10),
    ]
    # 몇 번을 실패해도 포기(None)하지 않고 10분을 넘지 않는다.
    for attempts in (5, 10, 100, 10_000):
        assert publish_retry_delay(attempts) == timedelta(minutes=10)


@pytest.mark.scenario("OUTBOX-TS-005")
def test_publish_plan_keeps_record_order_and_blocks_behind_a_waiting_event() -> None:
    from app.services.outbox.relay import plan_publish

    events = [pending_event(1, "42"), pending_event(2, "42"), pending_event(3, "42")]
    assert [event.id for event in plan_publish(events, NOW)] == [1, 2, 3]

    # 앞 이벤트(같은 대상)가 발행 실패로 다음 시도를 기다리면 뒤 이벤트도 발행하지 않는다.
    # 다른 대상의 이벤트는 막히지 않는다.
    waiting = pending_event(4, "7", next_publish_at=NOW + timedelta(seconds=30))
    later_same = pending_event(5, "7")
    other = pending_event(6, "8")
    assert [event.id for event in plan_publish([waiting, later_same, other], NOW)] == [6]
    assert [event.id for event in plan_publish([waiting, later_same, other], NOW + timedelta(seconds=30))] == [4, 5, 6]


# ------------------------------------------------------------------ 이벤트 봉투 (OUTBOX-REQ-008)


@pytest.mark.scenario("OUTBOX-TS-006")
def test_envelope_carries_kafka_ready_fields_and_aggregate_key() -> None:
    message = envelope().to_message()

    assert message == {
        "eventId": "8f0c7d6e-0000-4000-8000-000000000001",
        "eventType": "test.happened",
        "aggregateType": "test_aggregate",
        "aggregateId": "42",
        "schemaVersion": 1,
        "occurredAt": "2026-11-17T12:00:00.000000Z",
        "payload": {"value": 1},
    }
    assert envelope().key == "42"


# ------------------------------------------------------------------ 발행 지연 알림 (OUTBOX-REQ-003)


@pytest.mark.scenario("OUTBOX-TS-007")
def test_publish_delay_alerts_once_per_thirty_minutes_and_once_when_resolved() -> None:
    from app.services.outbox.monitor import PublishDelayMonitor

    alerts = RecordingAlerts()
    monitor = PublishDelayMonitor(alerts)

    # 4분 지연은 알리지 않는다.
    monitor.check(oldest_unpublished_at=NOW - timedelta(minutes=4), now=NOW)
    assert alerts.sent == []

    # 5분을 넘으면 1번 알리고, 같은 지연이 이어지는 10분 동안은 다시 알리지 않는다.
    start = NOW - timedelta(minutes=6)
    for minute in range(0, 11):
        monitor.check(oldest_unpublished_at=start, now=NOW + timedelta(minutes=minute))
    assert len(alerts.sent) == 1

    # 30분이 지나도 계속 밀려 있으면 한 번 더 알린다.
    monitor.check(oldest_unpublished_at=start, now=NOW + timedelta(minutes=31))
    assert len(alerts.sent) == 2

    # 지연이 풀리면 해소 알림을 1번 보내고, 이후 점검에서는 보내지 않는다.
    monitor.check(oldest_unpublished_at=None, now=NOW + timedelta(minutes=32))
    monitor.check(oldest_unpublished_at=None, now=NOW + timedelta(minutes=33))
    assert len(alerts.sent) == 3
    assert "해소" in alerts.sent[-1].headline


# ------------------------------------------------------------------ 전달 처리 (OUTBOX-REQ-004·005·006)


@pytest.mark.scenario("OUTBOX-TS-009")
@pytest.mark.parametrize("status_name", ["SUCCEEDED", "SKIPPED", "DEAD"])
def test_finished_delivery_is_never_claimed_again(status_name: str) -> None:
    from app.models.outbox import DeliveryStatus
    from app.services.outbox.delivery import is_claimable

    finished = SimpleNamespace(
        status=DeliveryStatus(status_name),
        next_attempt_at=None,
        locked_until=None,
    )
    assert is_claimable(finished, NOW + timedelta(days=1)) is False

    assert is_claimable(SimpleNamespace(status=DeliveryStatus.PENDING, next_attempt_at=None, locked_until=None), NOW)


@pytest.mark.scenario("OUTBOX-TS-011")
def test_default_policy_retries_five_times_with_backoff_then_dead() -> None:
    from app.models.outbox import DeliveryStatus
    from app.services.outbox.delivery import execute_delivery
    from app.services.outbox.policy import DEFAULT_RETRY_POLICY

    consumer = FailingConsumer(DEFAULT_RETRY_POLICY)
    expected_delays = [
        timedelta(seconds=5),
        timedelta(seconds=30),
        timedelta(minutes=2),
        timedelta(minutes=10),
        timedelta(minutes=10),
    ]

    now = NOW
    for attempts, delay in enumerate(expected_delays):
        outcome = execute_delivery(consumer, envelope(occurred_at=NOW), attempts=attempts, now=now)
        assert outcome.status == DeliveryStatus.FAILED
        assert outcome.next_attempt_at == now + delay
        assert outcome.error == "RuntimeError: 전달 실패"
        now = outcome.next_attempt_at

    final = execute_delivery(consumer, envelope(occurred_at=NOW), attempts=5, now=now)
    assert final.status == DeliveryStatus.DEAD
    assert final.next_attempt_at is None
    assert consumer.calls == 6  # 첫 시도 1번 + 재시도 5번


@pytest.mark.scenario("OUTBOX-TS-012")
def test_expired_delivery_is_skipped_without_calling_the_consumer() -> None:
    from app.models.outbox import DeliveryStatus
    from app.services.outbox.delivery import execute_delivery
    from app.services.outbox.policy import RetryPolicy

    consumer = FailingConsumer(RetryPolicy(max_retries=5, backoff=(timedelta(seconds=5),), expires_after=timedelta(minutes=10)))

    within = execute_delivery(consumer, envelope(occurred_at=NOW), attempts=2, now=NOW + timedelta(minutes=9, seconds=59))
    assert within.status == DeliveryStatus.FAILED

    expired = execute_delivery(consumer, envelope(occurred_at=NOW), attempts=3, now=NOW + timedelta(minutes=10, seconds=1))
    assert expired.status == DeliveryStatus.SKIPPED
    assert expired.skip_reason == "expired"
    assert consumer.calls == 1


@pytest.mark.scenario("OUTBOX-TS-013")
def test_dead_delivery_logs_and_alerts_once(caplog: pytest.LogCaptureFixture) -> None:
    from app.services.outbox.delivery import alert_dead_delivery

    alerts = RecordingAlerts()
    delivery = SimpleNamespace(id=7, consumer="test.failing", last_error="RuntimeError: 전달 실패", attempts=6, dead_alerted_at=None)

    with caplog.at_level(logging.ERROR):
        alert_dead_delivery(delivery, envelope(), alerts, NOW)
        alert_dead_delivery(delivery, envelope(), alerts, NOW + timedelta(minutes=1))

    assert len(alerts.sent) == 1
    text = alerts.sent[0].to_text()
    assert "test.failing" in text and "test.happened" in text and "42" in text
    assert delivery.dead_alerted_at == NOW
    assert any("test.failing" in record.getMessage() for record in caplog.records if record.levelno == logging.ERROR)


@pytest.mark.scenario("OUTBOX-TS-019")
def test_manual_retry_of_an_expired_delivery_ends_skipped() -> None:
    from app.models.outbox import DeliveryStatus
    from app.services.outbox.delivery import execute_delivery
    from app.services.outbox.policy import RetryPolicy

    consumer = FailingConsumer(RetryPolicy(max_retries=5, backoff=(timedelta(seconds=5),), expires_after=timedelta(minutes=10)))

    # 수동 재처리는 시도 횟수를 0으로 되돌리지만 유효 시간은 그대로 적용된다.
    outcome = execute_delivery(consumer, envelope(occurred_at=NOW), attempts=0, now=NOW + timedelta(hours=1))

    assert outcome.status == DeliveryStatus.SKIPPED
    assert outcome.skip_reason == "expired"
    assert consumer.calls == 0


# ------------------------------------------------------------------ 주기 작업 (OUTBOX-REQ-002·003·005·007)


@dataclass
class RecordingScheduler:
    jobs: list = field(default_factory=list)

    def add_job(self, func, trigger=None, **kwargs) -> None:
        self.jobs.append((func, trigger, kwargs))


@pytest.mark.scenario("OUTBOX-TS-022")
def test_outbox_registers_a_ten_second_cycle_and_a_daily_cleanup() -> None:
    from app.services.outbox import worker as outbox_worker

    scheduler = RecordingScheduler()
    worker = SimpleNamespace(run_cycle=lambda: None, cleanup=lambda: None)

    try:
        outbox_worker.register_outbox_jobs(scheduler, worker)

        jobs = {kwargs["id"]: (func, trigger, kwargs) for func, trigger, kwargs in scheduler.jobs}
        assert set(jobs) == {"outbox_cycle", "outbox_cleanup"}
        cycle_func, cycle_trigger, cycle_kwargs = jobs["outbox_cycle"]
        assert (cycle_func, cycle_trigger, cycle_kwargs["seconds"]) == (worker.run_cycle, "interval", 10)
        cleanup_func, cleanup_trigger, cleanup_kwargs = jobs["outbox_cleanup"]
        assert (cleanup_func, cleanup_trigger) == (worker.cleanup, "cron")
        assert (cleanup_kwargs["hour"], cleanup_kwargs["minute"]) == (4, 0)

        # 커밋 직후 깨우면 처리 작업을 바로 한 번 실행하도록 예약한다(정상 채팅은 10초를 기다리지 않는다).
        outbox_worker.wake_after_commit()
        func, trigger, kwargs = scheduler.jobs[-1]
        assert func is worker.run_cycle
        assert trigger is None  # 트리거가 없으면 APScheduler는 바로 한 번 실행한다
        assert kwargs["id"] == "outbox_cycle_now"
    finally:
        outbox_worker.set_wake_callback(None)


@pytest.mark.scenario("OUTBOX-TS-023")
def test_one_cycle_publishes_then_processes_deliveries_then_checks_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.outbox import worker as outbox_worker

    calls: list[str] = []
    publish_results = iter([100, 3, 0])

    def fake_publish(db, publisher, now):
        calls.append("publish")
        return next(publish_results)

    monkeypatch.setattr(outbox_worker, "publish_pending", fake_publish)
    delivery_results = iter([2, 1, 0])

    def fake_deliveries(db, registry, now, alert_sender):
        calls.append("deliveries")
        return next(delivery_results)

    monkeypatch.setattr(outbox_worker, "process_due_deliveries", fake_deliveries)
    monkeypatch.setattr(outbox_worker, "oldest_unpublished_at", lambda db: calls.append("oldest") or None)
    monkeypatch.setattr(outbox_worker, "get_admin_alert_sender", lambda: RecordingAlerts())

    session = SimpleNamespace(close=lambda: None, rollback=lambda: None)
    outbox_worker.OutboxWorker(lambda: session).run_cycle()

    # 같은 대상은 한 번에 하나씩 집으므로, 처리할 전달이 없을 때까지 이어서 처리한다
    assert calls == ["publish", "publish", "publish", "deliveries", "deliveries", "deliveries", "oldest"]
