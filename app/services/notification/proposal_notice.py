"""지원 전 취소·환불 알림. 업무 트랜잭션에 저장하고 라우터가 커밋 후 발송한다."""
import json

from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationStatus, NotificationType
from app.models.offer import Offer
from app.models.proposal import Proposal
from app.models.user import User
from app.services.notification_outbox import track_created_notification


_COPY = {
    NotificationType.PROPOSAL_CANCELLED_BY_USER: ("요청이 취소됐어요.", "요청이 취소됐어요."),
    NotificationType.PROPOSAL_CANCELLED_BY_ADMIN: ("요청이 취소됐어요.", "관리자에 의해 요청이 취소됐어요."),
    NotificationType.REFUND_COMPLETED: ("환불이 완료됐어요.", "행님에게 환불이 완료됐어요."),
}


def create_before_offer_notice(db: Session, proposal: Proposal, kind: NotificationType) -> None:
    # 취소된 지원도 이력이 있으면 채팅 경로다. 상태값/열린 방 수로 판단하지 않는다.
    # 호출자가 요청 행을 잠근 뒤 조회한다. 인증 등 이전 조회의 RR snapshot을
    # 재사용하지 않도록 잠금 조회로 최신 지원 이력을 읽는다.
    if db.query(Offer.id).filter(Offer.proposal_id == proposal.id).with_for_update().first() is not None:
        return
    user = db.get(User, proposal.orderer_id)
    title, body = _COPY[kind]
    enabled = user is not None and not user.deleted and user.alarm_enabled is True
    notice = Notification(
        user_id=proposal.orderer_id,
        notification_type=kind,
        title=title,
        body=body,
        related_entity_type="proposal",
        related_entity_id=proposal.id,
        data=json.dumps({"proposal_id": proposal.id}),
        status=NotificationStatus.PENDING if enabled else NotificationStatus.SKIPPED,
    )
    db.add(notice)
    track_created_notification(db, notice)
