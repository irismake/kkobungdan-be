"""채팅 푸시 전달 대상 `chat.push` (CHAT-REQ-018, docs/design-docs/chat-architecture.md "푸시").

`chat.message.created` 이벤트를 받아 받는 사람마다 FCM 푸시를 보낸다. `notifications`에는 저장하지 않는다.

- 받는 사람: 일반 채팅은 보낸 사람의 상대. 시스템 채팅은 `system_chat_delivery` 표에서 푸시 대상인 참여자.
- 알림이 꺼졌거나(`alarm_enabled`) 토큰이 없거나 탈퇴한 사람은 보내지 않는다. 보낼 사람이 없으면 `SKIPPED`.
- 제목은 기존 알림 제목(없으면 상대 이름), 내용은 받는 사람에게 보이는 채팅 문구, 배지는 채팅 안읽음 합계 + 알림 미읽음 수.
- 같은 채팅방 푸시는 묶음 키 `chat-room-{id}`로 이전 푸시를 대체한다. 그래서 재시도로 같은 푸시가 한 번 더
  나가도 사용자에게는 하나로 보인다(멱등).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Callable, Protocol

from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatMessageType, ChatRole, ChatRoom
from app.models.user import User, UserFCMToken
from app.schemas.notification import FCMSendResult
from app.services.chat.chat_room_service import display_name
from app.services.chat.system_chat import render_system_chat, render_system_title, system_chat_delivery
from app.services.notification.badge import badge_count
from app.services.outbox.consumers import SkipDelivery
from app.services.outbox.envelope import EventEnvelope
from app.services.outbox.policy import RetryPolicy

logger = logging.getLogger(__name__)

MESSAGE_CREATED = "chat.message.created"

#: 5회 재시도가 유효 시간 10분 안에 끝나도록 기본 간격보다 짧게 둔다 (event-delivery.md 전달 대상별 정책).
CHAT_PUSH_RETRY_POLICY = RetryPolicy(
    max_retries=5,
    backoff=(
        timedelta(seconds=5),
        timedelta(seconds=30),
        timedelta(minutes=1),
        timedelta(minutes=2),
        timedelta(minutes=4),
    ),
    expires_after=timedelta(minutes=10),
)


class PushSender(Protocol):
    def send(
        self,
        *,
        token: str,
        title: str,
        body: str,
        data: dict[str, str],
        collapse_key: str,
        badge: int,
    ) -> FCMSendResult: ...


class FCMPushSender:
    """FCMService로 보내는 실제 발송기."""

    def __init__(self, fcm_service) -> None:
        self._fcm = fcm_service

    def send(self, *, token: str, title: str, body: str, data: dict[str, str], collapse_key: str, badge: int) -> FCMSendResult:
        return self._fcm.send_notification(
            token=token, title=title, body=body, data=data, collapse_key=collapse_key, badge=badge
        )


class PushFailed(Exception):
    """FCM 발송 실패. 전달 처리가 재시도 정책대로 다시 시도한다."""


class ChatPushConsumer:
    name = "chat.push"
    event_types = frozenset({MESSAGE_CREATED})
    retry_policy = CHAT_PUSH_RETRY_POLICY

    def __init__(self, session_factory: Callable[[], Session], sender: PushSender) -> None:
        self._session_factory = session_factory
        self._sender = sender

    def handle(self, envelope: EventEnvelope) -> None:
        with self._session_factory() as db:
            message = db.get(ChatMessage, envelope.payload["messageId"])
            room = db.get(ChatRoom, envelope.payload["roomId"])
            if message is None or room is None:
                raise SkipDelivery("message_not_found")

            sent = 0
            failures: list[str] = []
            for role in _recipients(message, room):
                result = self._push(db, room, message, role)
                if result is None:
                    continue
                if result.success:
                    sent += 1
                else:
                    failures.append(f"{role.value}: {result.error_code} {result.error_message}")
            if failures:
                raise PushFailed("; ".join(failures))
            if sent == 0:
                raise SkipDelivery("no_recipient")

    def _push(self, db: Session, room: ChatRoom, message: ChatMessage, role: ChatRole) -> FCMSendResult | None:
        recipient_id = room.orderer_id if role == ChatRole.ORDERER else room.runner_id
        partner_id = room.runner_id if role == ChatRole.ORDERER else room.orderer_id
        recipient = db.get(User, recipient_id)
        if recipient is None or recipient.deleted or recipient.alarm_enabled is not True:
            return None
        token = db.query(UserFCMToken).filter(UserFCMToken.user_id == recipient_id).first()
        if token is None:
            return None
        title = display_name(db.get(User, partner_id))
        if message.type == ChatMessageType.SYSTEM:
            title = render_system_title(message.system_event, message.system_payload, role) or title
            body = render_system_chat(message.system_event, message.system_payload, role)
        else:
            body = message.content
        return self._sender.send(
            token=token.fcm_token,
            title=title,
            body=body,
            data={"type": "CHAT", "roomId": str(room.id), "messageId": str(message.id), "seq": str(message.seq)},
            collapse_key=f"chat-room-{room.id}",
            badge=badge_count(db, recipient_id),
        )


def _recipients(message: ChatMessage, room: ChatRoom) -> list[ChatRole]:
    if message.type == ChatMessageType.USER:
        return [ChatRole.RUNNER if message.sender_id == room.orderer_id else ChatRole.ORDERER]
    return [
        role
        for role in (ChatRole.ORDERER, ChatRole.RUNNER)
        if system_chat_delivery(message.system_event, role, message.system_payload)[1]
    ]


def register_chat_consumers(registry, session_factory: Callable[[], Session], fcm_service) -> None:
    """앱 시작 때 채팅 전달 대상(`chat.realtime`, `chat.push`)을 등록한다."""
    from app.realtime.hub import chat_hub
    from app.services.chat.chat_realtime import ChatRealtimeConsumer

    registry.register(ChatRealtimeConsumer(session_factory, chat_hub))
    registry.register(ChatPushConsumer(session_factory, FCMPushSender(fcm_service)))
