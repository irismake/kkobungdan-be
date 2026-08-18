"""Notification event listener — domain events → PENDING Notification records."""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session

from app.events.base import EventBus
from app.events.offer_events import OfferCreatedEvent, OfferAcceptedEvent
from app.events.proposal_events import (
    PaymentExpiredProposalCancelledEvent,
    PaymentReminderDueEvent,
    ProposalPaymentConfirmedEvent,
)
from app.events.execution_events import (
    DisputeRaisedByOrdererEvent,
    DisputeRaisedByRunnerEvent,
    MeetingConfirmedByOrdererEvent,
    MeetingConfirmedByRunnerEvent,
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


def _add_execution_completed_notifications(
    event: MeetingConfirmedByRunnerEvent | MeetingConfirmedByOrdererEvent,
    db: Session,
) -> None:
    bodies = (
        (event.orderer_id, "양측 만남이 모두 확인됐어요. 성공적으로 미션 수행이 완료됐습니다!"),
        (event.runner_id, "양측 만남이 모두 확인됐어요. 성공적으로 미션이 완료됐습니다!"),
    )
    for user_id, body in bodies:
        db.add(_pending(
            db=db,
            user_id=user_id,
            notification_type=NotificationType.EXECUTION_COMPLETED,
            title="미션 수행 완료! 수고하셨어요 🎊",
            body=body,
            related_entity_type="offer",
            related_entity_id=event.offer_id,
            status=_initial_status(db, user_id),
            data={"offer_id": event.offer_id, "proposal_id": event.proposal_id},
        ))


def on_offer_created(event: OfferCreatedEvent, db: Session) -> None:
    db.add(_pending(
        db=db,
        user_id=event.orderer_id,
        notification_type=NotificationType.OFFER_NEW,
        title="누군가 지원했어요! 👀",
        body="회원님의 요청에 새로운 꼬붕이 생겼어요. 확인해보세요!",
        related_entity_type="offer",
        related_entity_id=event.offer_id,
        status=_initial_status(db, event.orderer_id),
        data={"offer_id": event.offer_id, "proposal_id": event.proposal_id},
    ))

    db.add(_pending(
        db=db,
        user_id=event.runner_id,
        notification_type=NotificationType.OFFER_SUBMITTED,
        title="지원 완료! ✅",
        body="지원이 정상적으로 접수됐어요. 행님의 선택을 기다려주세요.",
        related_entity_type="offer",
        related_entity_id=event.offer_id,
        status=_initial_status(db, event.runner_id),
        data={"offer_id": event.offer_id, "proposal_id": event.proposal_id},
    ))


def on_offer_accepted(event: OfferAcceptedEvent, db: Session) -> None:
    db.add(_pending(
        db=db,
        user_id=event.orderer_id,
        notification_type=NotificationType.PROPOSAL_MATCHED,
        title="미션이 시작됐어요! 🏃",
        body="꼬붕을 선택하셨어요! 미션을 바로 시작해보세요.",
        related_entity_type="offer",
        related_entity_id=event.offer_id,
        status=_initial_status(db, event.orderer_id),
        data={"offer_id": event.offer_id, "proposal_id": event.proposal_id},
    ))

    db.add(_pending(
        db=db,
        user_id=event.accepted_runner_id,
        notification_type=NotificationType.OFFER_ACCEPTED,
        title="선택받으셨어요! 🙌",
        body="행님이 회원님을 선택했어요.",
        related_entity_type="offer",
        related_entity_id=event.offer_id,
        status=_initial_status(db, event.accepted_runner_id),
        data={"offer_id": event.offer_id, "proposal_id": event.proposal_id},
    ))

    for runner_id in event.rejected_runner_ids:
        db.add(_pending(
            db=db,
            user_id=runner_id,
            notification_type=NotificationType.OFFER_REJECTED,
            title="이번엔 아쉽게 됐어요 😢",
            body="이번엔 선택받지 못했지만 다음 기회가 분명 있을 거예요. 다시 도전해보세요!",
            related_entity_type="offer",
            related_entity_id=event.offer_id,
            status=_initial_status(db, runner_id),
            data={"offer_id": event.offer_id, "proposal_id": event.proposal_id},
        ))


def on_meeting_confirmed_by_runner(event: MeetingConfirmedByRunnerEvent, db: Session) -> None:
    if event.all_completed:
        _add_execution_completed_notifications(event, db)
        return

    db.add(_pending(
        db=db,
        user_id=event.orderer_id,
        notification_type=NotificationType.MEETING_CONFIRMED,
        title="꼬붕이 만남을 확인했어요! 🤝",
        body="꼬붕이 만남을 확인했어요. 회원님도 확인해주시면 수행비가 꼬붕에게 전달돼요.",
        related_entity_type="offer",
        related_entity_id=event.offer_id,
        status=_initial_status(db, event.orderer_id),
        data={"offer_id": event.offer_id, "proposal_id": event.proposal_id},
    ))


def on_meeting_confirmed_by_orderer(event: MeetingConfirmedByOrdererEvent, db: Session) -> None:
    if event.all_completed:
        _add_execution_completed_notifications(event, db)
        return

    db.add(_pending(
        db=db,
        user_id=event.runner_id,
        notification_type=NotificationType.MEETING_CONFIRMED,
        title="행님이 만남을 확인했어요! 🤝",
        body="행님이 만남을 확인했어요. 회원님도 앱에서 만남을 확인해주시면 정산이 바로 진행돼요!",
        related_entity_type="offer",
        related_entity_id=event.offer_id,
        status=_initial_status(db, event.runner_id),
        data={"offer_id": event.offer_id, "proposal_id": event.proposal_id},
    ))


def on_dispute_raised_by_orderer(event: DisputeRaisedByOrdererEvent, db: Session) -> None:
    db.add(_pending(
        db=db,
        user_id=event.runner_id,
        notification_type=NotificationType.DISPUTE_RAISED,
        title="분쟁이 접수되었어요 🚨",
        body="행님이 분쟁을 접수했어요. 앱에서 내용을 확인해주세요.",
        related_entity_type="offer",
        related_entity_id=event.offer_id,
        status=_initial_status(db, event.runner_id),
        data={"offer_id": event.offer_id, "proposal_id": event.proposal_id},
    ))


def on_dispute_raised_by_runner(event: DisputeRaisedByRunnerEvent, db: Session) -> None:
    db.add(_pending(
        db=db,
        user_id=event.orderer_id,
        notification_type=NotificationType.DISPUTE_RAISED,
        title="분쟁이 접수되었어요 🚨",
        body="꼬붕이 분쟁을 접수했어요. 앱에서 내용을 확인해주세요.",
        related_entity_type="offer",
        related_entity_id=event.offer_id,
        status=_initial_status(db, event.orderer_id),
        data={"offer_id": event.offer_id, "proposal_id": event.proposal_id},
    ))


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
    EventBus.register(OfferCreatedEvent, on_offer_created)
    EventBus.register(OfferAcceptedEvent, on_offer_accepted)
    EventBus.register(MeetingConfirmedByRunnerEvent, on_meeting_confirmed_by_runner)
    EventBus.register(MeetingConfirmedByOrdererEvent, on_meeting_confirmed_by_orderer)
    EventBus.register(DisputeRaisedByOrdererEvent, on_dispute_raised_by_orderer)
    EventBus.register(DisputeRaisedByRunnerEvent, on_dispute_raised_by_runner)
    EventBus.register(PaymentExpiredProposalCancelledEvent, on_payment_expired_proposal_cancelled)
    EventBus.register(ProposalPaymentConfirmedEvent, on_proposal_payment_confirmed)
    EventBus.register(PaymentReminderDueEvent, on_payment_reminder_due)
