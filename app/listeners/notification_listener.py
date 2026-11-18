"""Notification event listener — domain events → PENDING Notification records."""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session

from app.events.base import EventBus
from app.events.proposal_events import (
    PaymentExpiredProposalCancelledEvent,
    PaymentReminderDueEvent,
    ProposalPaymentConfirmedEvent,
)
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.models.user import User
from app.services.notification_outbox import track_created_notification

logger = logging.getLogger(__name__)


def _alarm_enabled(db: Session, user_id: str) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    return user is not None and user.alarm_enabled is True


def _initial_status(db: Session, user_id: str) -> NotificationStatus:
    return NotificationStatus.PENDING if _alarm_enabled(db, user_id) else NotificationStatus.SKIPPED


def _pending(
    db: Session,
    user_id: str,
    notification_type: NotificationType,
    title: str,
    body: str,
    related_entity_type: str,
    related_entity_id: int,
    status: NotificationStatus,
    data: dict | None = None,
) -> Notification:
    import json
    notification = Notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        body=body,
        data=json.dumps(data) if data else None,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        status=status,
    )
    track_created_notification(db, notification)
    return notification


def on_payment_expired_proposal_cancelled(event: PaymentExpiredProposalCancelledEvent, db: Session) -> None:
    db.add(_pending(
        db=db,
        user_id=event.orderer_id,
        notification_type=NotificationType.PROPOSAL_CANCELLED,
        title=f"{event.proposal_title} 요청이 24시간 내 미입금으로 취소됐어요. 다시 등록해주세요. 😢",
        body="24시간 이내 입금이 확인되지 않아 요청이 취소 되었어요. 다시 요청 게시글을 올려주세요.",
        related_entity_type="proposal",
        related_entity_id=event.proposal_id,
        status=_initial_status(db, event.orderer_id),
        data={"proposal_id": event.proposal_id},
    ))


def on_proposal_payment_confirmed(event: ProposalPaymentConfirmedEvent, db: Session) -> None:
    db.add(_pending(
        db=db,
        user_id=event.orderer_id,
        notification_type=NotificationType.PAYMENT_COMPLETED,
        title="게시물이 등록됐어요! 🎉",
        body="입금이 확인됐어요. 지금 바로 꼬붕을 기다려보세요!",
        related_entity_type="proposal",
        related_entity_id=event.proposal_id,
        status=_initial_status(db, event.orderer_id),
        data={"proposal_id": event.proposal_id},
    ))


def on_payment_reminder_due(event: PaymentReminderDueEvent, db: Session) -> None:
    db.add(_pending(
        db=db,
        user_id=event.orderer_id,
        notification_type=NotificationType.PAYMENT_REMINDER,
        title="입금이 아직 확인되지 않았어요 🔍",
        body="입금이 확인되지 않아 게시물이 등록되지 않았어요. 입금 내역 확인 후 다시 시도해주세요.",
        related_entity_type="proposal",
        related_entity_id=event.proposal_id,
        status=_initial_status(db, event.orderer_id),
        data={"proposal_id": event.proposal_id},
    ))


def register_all() -> None:
    EventBus.register(PaymentExpiredProposalCancelledEvent, on_payment_expired_proposal_cancelled)
    EventBus.register(ProposalPaymentConfirmedEvent, on_proposal_payment_confirmed)
    EventBus.register(PaymentReminderDueEvent, on_payment_reminder_due)
