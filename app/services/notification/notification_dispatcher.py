"""Notification dispatcher — sends ad-hoc custom notifications via FCM.

도메인 이벤트 기반 알림은 `app/listeners/notification_listener.py`가 처리한다.
이 클래스는 테스트 알림 발송 엔드포인트에서만 사용한다.
"""
import logging
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationType
from app.services.fcm_service import FCMService


logger = logging.getLogger(__name__)


class NotificationDispatcher:
    def __init__(self, fcm_service: FCMService):
        self.fcm_service = fcm_service

    def send_custom_notification(
        self, db: Session, user_id: str, title: str, body: str,
        data: Optional[Dict[str, Any]] = None, related_entity_type: Optional[str] = None,
        related_entity_id: Optional[int] = None, image: Optional[str] = None,
    ) -> Notification:
        notification, _ = self.fcm_service.send_to_user(
            db=db, user_id=user_id, notification_type=NotificationType.CUSTOM,
            title=title, body=body, data=data,
            related_entity_type=related_entity_type, related_entity_id=related_entity_id, image=image,
        )
        return notification
