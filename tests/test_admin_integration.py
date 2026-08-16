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
    assert "만료 요청" in notification.body


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
