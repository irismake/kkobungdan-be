"""안읽음 수 계산 (CHAT-REQ-011). 저장하지 않고 읽음 위치와 저장된 채팅으로 계산한다."""

from __future__ import annotations

from sqlalchemy import and_, func, not_, or_
from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatMessageType, ChatRole, ChatRoom, SystemChatEvent

#: 보는 사람별로 안읽음에서 빼는 시스템 채팅 (CHAT-REQ-021 표의 "안읽음·푸시 모두 제외")
_EXCLUDED_SYSTEM_EVENTS: dict[ChatRole, tuple[SystemChatEvent, ...]] = {
    ChatRole.ORDERER: (SystemChatEvent.NOT_SELECTED,),
    ChatRole.RUNNER: (),
}


def last_read_seq(room: ChatRoom, role: ChatRole) -> int:
    return room.orderer_last_read_seq if role == ChatRole.ORDERER else room.runner_last_read_seq


def unread_count(db: Session, room: ChatRoom, viewer_id: str, role: ChatRole) -> int:
    condition = [
        ChatMessage.room_id == room.id,
        ChatMessage.seq > last_read_seq(room, role),
        not_(and_(ChatMessage.type == ChatMessageType.USER, ChatMessage.sender_id == viewer_id)),
    ]
    excluded = _EXCLUDED_SYSTEM_EVENTS[role]
    if excluded:
        condition.append(
            or_(ChatMessage.type != ChatMessageType.SYSTEM, ChatMessage.system_event.notin_(list(excluded)))
        )
    return db.query(func.count(ChatMessage.id)).filter(*condition).scalar() or 0
