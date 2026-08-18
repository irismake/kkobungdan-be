from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.tasks import payment_checker
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.models.offer import OfferStatus
from app.models.proposal import ProposalStatus
from app.services.proposal.proposal_service import ProposalService


def test_confirm_payment_posts_holding_proposal_without_request_body(client, db, factory, sample_user):
    proposal = factory.proposal(sample_user.id, ProposalStatus.HOLDING)

    response = client.post(f"/v1/admin/proposal/{proposal.id}/confirm-payment")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "POSTED"
    db.refresh(proposal)
    assert proposal.status == ProposalStatus.POSTED


def test_confirm_payment_notifies_orderer(client, db, factory, sample_user):
    sample_user.alarm_enabled = True
    proposal = factory.proposal(sample_user.id, ProposalStatus.HOLDING)
    db.commit()

    response = client.post(f"/v1/admin/proposal/{proposal.id}/confirm-payment")

    assert response.status_code == 200
    notification = (
        db.query(Notification)
        .filter(Notification.notification_type == NotificationType.PAYMENT_COMPLETED)
        .one()
    )
    assert notification.user_id == sample_user.id
    assert notification.title == "게시물이 등록됐어요! 🎉"
    assert notification.related_entity_id == proposal.id
    assert notification.status == NotificationStatus.PENDING


def test_send_payment_reminders_targets_only_pending_payments_once(db, factory, sample_user):
    now = datetime(2026, 6, 2, 12, 0, 0)
    sample_user.alarm_enabled = True
    due = factory.proposal(sample_user.id, ProposalStatus.HOLDING, "독촉 대상")
    too_fresh = factory.proposal(sample_user.id, ProposalStatus.HOLDING, "30분 미경과")
    past_deadline = factory.proposal(sample_user.id, ProposalStatus.HOLDING, "24시간 초과")
    already_paid = factory.proposal(sample_user.id, ProposalStatus.POSTED, "입금 완료")

    due.created_at = now - timedelta(minutes=31)
    too_fresh.created_at = now - timedelta(minutes=29)
    past_deadline.created_at = now - timedelta(hours=24, minutes=1)
    already_paid.created_at = now - timedelta(hours=2)
    db.commit()

    assert ProposalService.send_payment_reminders(db, now=now) == 1

    notification = (
        db.query(Notification)
        .filter(Notification.notification_type == NotificationType.PAYMENT_REMINDER)
        .one()
    )
    assert notification.related_entity_id == due.id
    assert notification.title == "입금이 아직 확인되지 않았어요 🔍"

    # 재실행해도 같은 Proposal에 중복 발송하지 않는다.
    assert ProposalService.send_payment_reminders(db, now=now) == 0
    assert (
        db.query(Notification)
        .filter(Notification.notification_type == NotificationType.PAYMENT_REMINDER)
        .count()
        == 1
    )


def test_send_payment_reminders_skips_notification_when_alarm_disabled(db, factory, sample_user):
    now = datetime(2026, 6, 2, 12, 0, 0)
    sample_user.alarm_enabled = False
    due = factory.proposal(sample_user.id, ProposalStatus.HOLDING, "독촉 대상")
    due.created_at = now - timedelta(minutes=31)
    db.commit()

    assert ProposalService.send_payment_reminders(db, now=now) == 1

    notification = (
        db.query(Notification)
        .filter(Notification.notification_type == NotificationType.PAYMENT_REMINDER)
        .one()
    )
    assert notification.status == NotificationStatus.SKIPPED


def test_confirm_payment_rejects_non_holding_proposal(client, db, factory, sample_user):
    proposal = factory.proposal(sample_user.id, ProposalStatus.POSTED)

    response = client.post(f"/v1/admin/proposal/{proposal.id}/confirm-payment")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_STATUS"


def test_cancel_expired_payment_proposals_only_cancels_holding_after_24_hours(db, factory, sample_user):
    now = datetime(2026, 6, 2, 12, 0, 0)
    expired_holding = factory.proposal(sample_user.id, ProposalStatus.HOLDING, "expired")
    boundary_holding = factory.proposal(sample_user.id, ProposalStatus.HOLDING, "boundary")
    fresh_holding = factory.proposal(sample_user.id, ProposalStatus.HOLDING, "fresh")
    expired_posted = factory.proposal(sample_user.id, ProposalStatus.POSTED, "posted")

    expired_holding.created_at = now - timedelta(hours=24, minutes=1)
    boundary_holding.created_at = now - timedelta(hours=24)
    fresh_holding.created_at = now - timedelta(hours=23, minutes=59)
    expired_posted.created_at = now - timedelta(hours=24, minutes=1)
    db.commit()

    cancelled_count = ProposalService.cancel_expired_payment_proposals(db, now=now)

    assert cancelled_count == 2
    db.refresh(expired_holding)
    db.refresh(boundary_holding)
    db.refresh(fresh_holding)
    db.refresh(expired_posted)
    assert expired_holding.status == ProposalStatus.CANCELLED
    assert boundary_holding.status == ProposalStatus.CANCELLED
    assert fresh_holding.status == ProposalStatus.HOLDING
    assert expired_posted.status == ProposalStatus.POSTED


def test_cancel_expired_payment_proposals_notifies_orderer(db, factory, sample_user):
    now = datetime(2026, 6, 2, 12, 0, 0)
    sample_user.alarm_enabled = True
    expired = factory.proposal(sample_user.id, ProposalStatus.HOLDING, "만료 요청")
    fresh = factory.proposal(sample_user.id, ProposalStatus.HOLDING, "정상 요청")
    expired.created_at = now - timedelta(hours=24, minutes=1)
    fresh.created_at = now - timedelta(hours=1)
    db.commit()

    ProposalService.cancel_expired_payment_proposals(db, now=now)

    notifications = (
        db.query(Notification)
        .filter(Notification.notification_type == NotificationType.PROPOSAL_CANCELLED)
        .all()
    )
    assert len(notifications) == 1
    notification = notifications[0]
    assert notification.user_id == sample_user.id
    assert notification.related_entity_type == "proposal"
    assert notification.related_entity_id == expired.id
    assert notification.status == NotificationStatus.PENDING
    assert notification.title == "입금이 완료 되지 않아 요청이 취소되었어요. 😢"
    assert notification.body.startswith("만료 요청 요청이 24시간 내 미입금으로")


def test_cancel_expired_payment_proposals_skips_notification_when_alarm_disabled(db, factory, sample_user):
    now = datetime(2026, 6, 2, 12, 0, 0)
    sample_user.alarm_enabled = False
    expired = factory.proposal(sample_user.id, ProposalStatus.HOLDING, "만료 요청")
    expired.created_at = now - timedelta(hours=24, minutes=1)
    db.commit()

    ProposalService.cancel_expired_payment_proposals(db, now=now)

    notification = (
        db.query(Notification)
        .filter(Notification.notification_type == NotificationType.PROPOSAL_CANCELLED)
        .one()
    )
    assert notification.status == NotificationStatus.SKIPPED


def test_cancel_expired_payment_proposals_creates_no_notification_when_nothing_expired(db, factory, sample_user):
    now = datetime(2026, 6, 2, 12, 0, 0)
    fresh = factory.proposal(sample_user.id, ProposalStatus.HOLDING, "정상 요청")
    fresh.created_at = now - timedelta(hours=1)
    db.commit()

    assert ProposalService.cancel_expired_payment_proposals(db, now=now) == 0
    assert db.query(Notification).count() == 0


def test_payment_checker_closes_session_and_returns_cancelled_count(monkeypatch):
    class FakeSession:
        closed = False
        info: dict = {}

        def close(self):
            self.closed = True

    fake_session = FakeSession()

    def fake_cancel(db):
        assert db is fake_session
        return 3

    monkeypatch.setattr(payment_checker.ProposalService, "cancel_expired_payment_proposals", fake_cancel)

    cancelled_count = payment_checker.check_and_cancel_expired_payment_proposals(lambda: fake_session)

    assert cancelled_count == 3
    assert fake_session.closed is True


def test_list_pending_payment_proposals_without_auth(client, factory, sample_user):
    holding = factory.proposal(sample_user.id, ProposalStatus.HOLDING)
    factory.proposal(sample_user.id, ProposalStatus.POSTED)

    response = client.get("/v1/admin/proposal/pending-payment")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["data"]] == [holding.id]


def test_resolve_offer_sets_resolved_from_disputed(client, db, factory, sample_user):
    runner = factory.user("01066660003")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.DISPUTED, OfferStatus.DISPUTED)
    disputed_at = datetime.now(timezone.utc)
    proposal.disputed_at = disputed_at
    offer.disputed_at = disputed_at
    db.commit()

    response = client.post(f"/v1/admin/offer/{offer.id}/resolve")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "RESOLVED"
    assert response.json()["data"]["resolvedAt"] is not None
    db.refresh(proposal)
    db.refresh(offer)
    assert proposal.status == ProposalStatus.RESOLVED
    assert offer.status == OfferStatus.RESOLVED
    assert proposal.resolved_at is not None
    assert offer.resolved_at is not None
    assert proposal.disputed_at is not None
    assert offer.disputed_at is not None
