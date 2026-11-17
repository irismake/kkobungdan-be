"""Outbox 통합 테스트 (MySQL: 같은 트랜잭션 기록, 발행, 전달 처리, 관리자 재처리, 정리).

시나리오 정본: docs/domains/outbox/test-scenarios.md 의 OUTBOX-TS-*
설계: docs/design-docs/outbox.md
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pytest

from tests.conftest import TestSessionLocal

NOW = datetime(2026, 11, 17, 12, 0, 0)


# ------------------------------------------------------------------ 테스트용 발행자·전달 대상


@dataclass
class RecordingPublisher:
    published: list = field(default_factory=list)
    delay: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def publish(self, envelope, db) -> None:
        if self.delay:
            time.sleep(self.delay)
        with self.lock:
            self.published.append(envelope)


@dataclass
class RecordingAlerts:
    sent: list = field(default_factory=list)

    def send(self, alert) -> None:
        self.sent.append(alert)


class TestConsumer:
    __test__ = False  # pytest가 테스트 클래스로 모으지 않게 한다

    def __init__(self, name: str, fail_times: int = 0):
        from app.services.outbox.policy import DEFAULT_RETRY_POLICY

        self.name = name
        self.event_types = frozenset({"test.happened"})
        self.retry_policy = DEFAULT_RETRY_POLICY
        self.fail_times = fail_times
        self.calls = 0

    def handle(self, envelope) -> None:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(f"{self.name} 실패")


def registry_of(*consumers):
    from app.services.outbox.consumers import ConsumerRegistry

    registry = ConsumerRegistry()
    for consumer in consumers:
        registry.register(consumer)
    return registry


def record(db, aggregate_id: str = "42", occurred_at: datetime = NOW, payload: dict | None = None):
    from app.services.outbox.writer import record_event

    return record_event(
        db,
        event_type="test.happened",
        aggregate_type="test_aggregate",
        aggregate_id=aggregate_id,
        payload=payload or {"value": 1},
        occurred_at=occurred_at,
    )


def make_delivery(db, consumer: str, status_name: str, *, finished_at: datetime | None = NOW, aggregate_id: str = "42"):
    """정해진 상태의 전달 1건을 직접 만든다(발행 완료된 이벤트 포함)."""
    from app.models.outbox import DeliveryStatus, EventDelivery

    event = record(db, aggregate_id=aggregate_id)
    event.published_at = NOW
    db.flush()
    status = DeliveryStatus(status_name)
    delivery = EventDelivery(
        event_id=event.event_id,
        consumer=consumer,
        status=status,
        attempts=6 if status == DeliveryStatus.DEAD else 1,
        last_error="RuntimeError: 실패" if status == DeliveryStatus.DEAD else None,
        locked_until=NOW + timedelta(minutes=5) if status == DeliveryStatus.PROCESSING else None,
        finished_at=finished_at if status in {DeliveryStatus.SUCCEEDED, DeliveryStatus.SKIPPED, DeliveryStatus.DEAD} else None,
    )
    db.add(delivery)
    db.commit()
    return delivery


def run_in_threads(target, count: int = 2):
    barrier = threading.Barrier(count)
    results: list = [None] * count
    errors: list = [None] * count

    def runner(index: int) -> None:
        session = TestSessionLocal()
        try:
            barrier.wait()
            results[index] = target(session)
        except Exception as exc:  # noqa: BLE001 - 스레드 결과로 넘긴다
            errors[index] = exc
            session.rollback()
        finally:
            session.close()

    threads = [threading.Thread(target=runner, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results, errors


# ------------------------------------------------------------------ 기록 (OUTBOX-REQ-001)


@pytest.mark.scenario("OUTBOX-TS-001")
def test_event_is_recorded_only_with_a_committed_state_change(db, sample_user):
    from app.models.outbox import OutboxEvent
    from app.models.user import User

    sample_user.name = "바뀐 이름"
    record(db, payload={"name": "바뀐 이름"})
    db.commit()

    events = db.query(OutboxEvent).all()
    assert len(events) == 1
    assert events[0].published_at is None
    assert events[0].event_type == "test.happened"
    assert db.get(User, sample_user.id).name == "바뀐 이름"

    sample_user.name = "롤백될 이름"
    record(db, payload={"name": "롤백될 이름"})
    db.rollback()

    assert db.query(OutboxEvent).count() == 1
    assert db.get(User, sample_user.id).name == "바뀐 이름"


# ------------------------------------------------------------------ 발행 (OUTBOX-REQ-002)


@pytest.mark.scenario("OUTBOX-TS-002")
def test_periodic_relay_publishes_leftover_events_in_record_order(db):
    from app.models.outbox import OutboxEvent
    from app.services.outbox.relay import publish_pending

    first = record(db, aggregate_id="1")
    second = record(db, aggregate_id="2")
    third = record(db, aggregate_id="1")
    db.commit()  # 커밋 후 바로 발행하지 못한 상태(서버 중단 가정)

    publisher = RecordingPublisher()
    published_count = publish_pending(db, publisher, now=NOW)

    assert published_count == 3
    assert [envelope.event_id for envelope in publisher.published] == [first.event_id, second.event_id, third.event_id]
    db.expire_all()
    assert all(event.published_at is not None for event in db.query(OutboxEvent).all())
    assert publish_pending(db, publisher, now=NOW) == 0


@pytest.mark.scenario("OUTBOX-TS-004")
def test_concurrent_relays_publish_each_event_exactly_once(db):
    from app.models.outbox import OutboxEvent
    from app.services.outbox.relay import publish_pending

    events = [record(db, aggregate_id=str(index)) for index in range(5)]
    db.commit()

    publisher = RecordingPublisher(delay=0.05)
    results, errors = run_in_threads(lambda session: publish_pending(session, publisher, now=NOW))

    assert errors == [None, None]
    assert sum(results) == 5
    assert sorted(envelope.event_id for envelope in publisher.published) == sorted(event.event_id for event in events)
    db.expire_all()
    assert db.query(OutboxEvent).filter(OutboxEvent.published_at.is_(None)).count() == 0


# ------------------------------------------------------------------ 전달 처리 (OUTBOX-REQ-004·005)


@pytest.mark.scenario("OUTBOX-TS-008")
def test_consumers_are_processed_and_retried_independently(db):
    from app.models.outbox import DeliveryStatus, EventDelivery
    from app.services.outbox.delivery import process_due_deliveries
    from app.services.outbox.publisher import InProcessEventPublisher
    from app.services.outbox.relay import publish_pending

    consumer_a = TestConsumer("test.a")
    consumer_b = TestConsumer("test.b", fail_times=1)
    registry = registry_of(consumer_a, consumer_b)
    alerts = RecordingAlerts()
    event = record(db)
    db.commit()

    publish_pending(db, InProcessEventPublisher(registry), now=NOW)
    process_due_deliveries(db, registry, now=NOW, alert_sender=alerts)

    deliveries = {d.consumer: d for d in db.query(EventDelivery).filter(EventDelivery.event_id == event.event_id)}
    assert deliveries["test.a"].status == DeliveryStatus.SUCCEEDED
    assert deliveries["test.b"].status == DeliveryStatus.FAILED
    assert deliveries["test.b"].next_attempt_at == NOW + timedelta(seconds=5)

    process_due_deliveries(db, registry, now=NOW + timedelta(seconds=10), alert_sender=alerts)

    db.expire_all()
    deliveries = {d.consumer: d for d in db.query(EventDelivery).filter(EventDelivery.event_id == event.event_id)}
    assert deliveries["test.b"].status == DeliveryStatus.SUCCEEDED
    assert consumer_a.calls == 1
    assert consumer_b.calls == 2


@pytest.mark.scenario("OUTBOX-TS-010")
def test_processing_delivery_is_leased_and_reclaimed_after_five_minutes(db):
    from app.models.outbox import DeliveryStatus, EventDelivery
    from app.services.outbox.delivery import claim_due_deliveries

    delivery = make_delivery(db, "test.a", "PENDING", finished_at=None)

    claimed = claim_due_deliveries(TestSessionLocal(), now=NOW)
    assert [d.id for d in claimed] == [delivery.id]

    db.expire_all()
    stored = db.get(EventDelivery, delivery.id)
    assert stored.status == DeliveryStatus.PROCESSING
    assert stored.locked_until == NOW + timedelta(minutes=5)

    assert claim_due_deliveries(TestSessionLocal(), now=NOW + timedelta(minutes=1)) == []
    assert [d.id for d in claim_due_deliveries(TestSessionLocal(), now=NOW + timedelta(minutes=6))] == [delivery.id]


# ------------------------------------------------------------------ DEAD와 수동 재처리 (OUTBOX-REQ-006)


@pytest.mark.scenario("OUTBOX-TS-014")
def test_admin_lists_dead_deliveries_by_consumer_and_period(client, db, admin_headers):
    recent = make_delivery(db, "test.a", "DEAD", finished_at=NOW)
    make_delivery(db, "test.a", "DEAD", finished_at=NOW - timedelta(days=3))
    make_delivery(db, "test.b", "DEAD", finished_at=NOW)
    make_delivery(db, "test.a", "SUCCEEDED", finished_at=NOW)

    response = client.get(
        "/v1/admin/outbox/deliveries",
        params={"consumer": "test.a", "from": "2026-11-17T00:00:00Z", "to": "2026-11-18T00:00:00Z"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    content = response.json()["data"]["content"]
    assert [item["id"] for item in content] == [recent.id]
    item = content[0]
    assert item["status"] == "DEAD"
    assert item["consumer"] == "test.a"
    assert item["eventType"] == "test.happened"
    assert item["aggregateId"] == "42"
    assert item["attempts"] == 6
    assert item["lastError"] == "RuntimeError: 실패"


@pytest.mark.scenario("OUTBOX-TS-015")
def test_admin_retry_resets_attempts_and_reprocesses(client, db, admin_user, admin_headers):
    from app.models.outbox import DeliveryStatus, EventDelivery
    from app.services.outbox.delivery import process_due_deliveries

    delivery = make_delivery(db, "test.a", "DEAD")

    response = client.post(f"/v1/admin/outbox/deliveries/{delivery.id}/retry", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "PENDING"
    assert data["attempts"] == 0
    assert data["manualRetryCount"] == 1
    db.expire_all()
    stored = db.get(EventDelivery, delivery.id)
    assert stored.last_manual_retry_by == admin_user.id
    assert stored.dead_alerted_at is None

    consumer = TestConsumer("test.a")
    process_due_deliveries(db, registry_of(consumer), now=NOW + timedelta(seconds=1), alert_sender=RecordingAlerts())
    db.expire_all()
    assert db.get(EventDelivery, delivery.id).status == DeliveryStatus.SUCCEEDED
    assert consumer.calls == 1


@pytest.mark.scenario("OUTBOX-TS-016")
@pytest.mark.parametrize("status_name", ["SUCCEEDED", "SKIPPED", "PROCESSING"])
def test_admin_cannot_retry_a_delivery_that_is_not_dead(client, db, admin_headers, status_name):
    from app.models.outbox import DeliveryStatus, EventDelivery

    delivery = make_delivery(db, "test.a", status_name)

    response = client.post(f"/v1/admin/outbox/deliveries/{delivery.id}/retry", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OUTBOX_DELIVERY_NOT_RETRYABLE"
    db.expire_all()
    stored = db.get(EventDelivery, delivery.id)
    assert stored.status == DeliveryStatus(status_name)
    assert stored.manual_retry_count == 0


@pytest.mark.scenario("OUTBOX-TS-017")
def test_concurrent_admin_retries_reprocess_only_once(db, admin_user):
    from app.models.outbox import DeliveryStatus, EventDelivery
    from app.services.outbox.admin import OutboxAdminService

    delivery = make_delivery(db, "test.a", "DEAD")

    results, errors = run_in_threads(lambda session: OutboxAdminService.retry_delivery(session, delivery.id, admin_user.id))

    assert sum(result is not None for result in results) == 1
    assert sum(error is not None for error in errors) == 1
    db.expire_all()
    stored = db.get(EventDelivery, delivery.id)
    assert stored.status == DeliveryStatus.PENDING
    assert stored.manual_retry_count == 1


@pytest.mark.scenario("OUTBOX-TS-018")
def test_admin_bulk_retry_only_touches_the_given_consumer(client, db, admin_headers):
    from app.models.outbox import DeliveryStatus, EventDelivery

    targets = [make_delivery(db, "test.a", "DEAD", aggregate_id=str(index)) for index in range(3)]
    other = make_delivery(db, "test.b", "DEAD")

    response = client.post("/v1/admin/outbox/deliveries/retry", params={"consumer": "test.a"}, headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["data"] == {"consumer": "test.a", "retriedCount": 3}
    db.expire_all()
    assert {db.get(EventDelivery, d.id).status for d in targets} == {DeliveryStatus.PENDING}
    assert db.get(EventDelivery, other.id).status == DeliveryStatus.DEAD


@pytest.mark.scenario("OUTBOX-TS-020")
def test_non_admin_cannot_list_or_retry_deliveries(client, db, auth_headers):
    delivery = make_delivery(db, "test.a", "DEAD")

    requests = [
        client.get("/v1/admin/outbox/deliveries", headers=auth_headers),
        client.post(f"/v1/admin/outbox/deliveries/{delivery.id}/retry", headers=auth_headers),
        client.post("/v1/admin/outbox/deliveries/retry", params={"consumer": "test.a"}, headers=auth_headers),
    ]

    for response in requests:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"


# ------------------------------------------------------------------ 정리 (OUTBOX-REQ-007)


@pytest.mark.scenario("OUTBOX-TS-021")
def test_cleanup_deletes_only_events_finished_more_than_seven_days_ago(db):
    from app.models.outbox import DeliveryStatus, EventDelivery, OutboxEvent
    from app.services.outbox.cleanup import cleanup_finished_events

    old_done = make_delivery(db, "test.a", "SUCCEEDED", finished_at=NOW - timedelta(days=8), aggregate_id="old")
    # 같은 이벤트의 다른 전달 대상도 끝난 지 8일
    db.add(EventDelivery(event_id=old_done.event_id, consumer="test.b", status=DeliveryStatus.SKIPPED, finished_at=NOW - timedelta(days=8)))
    recent_done = make_delivery(db, "test.a", "SUCCEEDED", finished_at=NOW - timedelta(days=6), aggregate_id="recent")
    dead = make_delivery(db, "test.a", "DEAD", finished_at=NOW - timedelta(days=30), aggregate_id="dead")
    failed = make_delivery(db, "test.a", "FAILED", finished_at=None, aggregate_id="failed")
    unpublished = record(db, aggregate_id="unpublished")
    db.commit()

    deleted = cleanup_finished_events(db, now=NOW)

    assert deleted == 1
    db.expire_all()
    remaining_events = {event.event_id for event in db.query(OutboxEvent).all()}
    assert old_done.event_id not in remaining_events
    assert {recent_done.event_id, dead.event_id, failed.event_id, unpublished.event_id} <= remaining_events
    assert db.query(EventDelivery).filter(EventDelivery.event_id == old_done.event_id).count() == 0
