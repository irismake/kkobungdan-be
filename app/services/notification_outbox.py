"""Helpers for tracking notifications created in the current DB unit of work."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationStatus


_SESSION_KEY = "created_notifications"


def track_created_notification(db: Session, notification: Notification) -> None:
    db.info.setdefault(_SESSION_KEY, []).append(notification)


def pop_pending_notification_ids(db: Session) -> list[int]:
    notifications = db.info.pop(_SESSION_KEY, [])
    return [
        notification.id
        for notification in notifications
        if notification.id is not None and notification.status == NotificationStatus.PENDING
    ]
