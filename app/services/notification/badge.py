"""앱 아이콘 배지 숫자 (CHAT-REQ-018). 채팅 푸시와 기존 알림 푸시가 같은 값을 보낸다."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.notification import Notification


def badge_count(db: Session, user_id: str) -> int:
    """채팅 전체 안읽음 합계 + 알림 미읽음 수."""
    from app.services.chat.chat_read_service import ChatReadService

    chat_unread = ChatReadService.unread_summary(db, user_id).total_unread_count
    notification_unread = (
        db.query(Notification).filter(Notification.user_id == user_id, Notification.read_at.is_(None)).count()
    )
    return chat_unread + notification_unread
