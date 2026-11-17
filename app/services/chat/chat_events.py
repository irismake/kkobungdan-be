"""채팅 이벤트 기록 (CHAT-REQ-029, docs/design-docs/chat-architecture.md "채팅 이벤트").

채팅 서비스는 WebSocket·FCM을 직접 부르지 않고 여기서 Outbox에 기록만 한다. 실제 전달은
전달 대상(chat.realtime, chat.push)이 한다. 모두 aggregate = 채팅방이라 채팅방 안 순서가 지켜진다.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatRoom
from app.services.outbox.writer import record_event

AGGREGATE_TYPE = "chat_room"
MESSAGE_CREATED = "chat.message.created"


def record_message_created(db: Session, room: ChatRoom, message: ChatMessage) -> None:
    """채팅(일반·시스템)이 저장됐다. `message.id`가 있어야 하므로 호출 전에 flush한다."""
    record_event(
        db,
        event_type=MESSAGE_CREATED,
        aggregate_type=AGGREGATE_TYPE,
        aggregate_id=room.id,
        payload={
            "roomId": room.id,
            "messageId": message.id,
            "seq": message.seq,
            "type": message.type.value,
            "senderId": message.sender_id,
            "systemEvent": message.system_event.value if message.system_event else None,
        },
        occurred_at=message.created_at,
    )
