"""채팅 조회 (CHAT-REQ-004)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatMessageType, ChatRole
from app.schemas.chat import ChatMessageListResponse, ChatMessageResponse
from app.services.chat.chat_room_service import ChatRoomService
from app.services.chat.system_chat import render_system_chat

PAGE_SIZE = 30


class ChatMessageService:
    @staticmethod
    def list_latest(db: Session, room_id: int, user_id: str) -> ChatMessageListResponse:
        """최근 채팅 30개를 저장 순서대로 돌려준다."""
        room, role = ChatRoomService.get_room_for_participant(db, room_id, user_id)
        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.room_id == room.id)
            .order_by(ChatMessage.seq.desc())
            .limit(PAGE_SIZE + 1)
            .all()
        )
        has_previous = len(rows) > PAGE_SIZE
        page = list(reversed(rows[:PAGE_SIZE]))
        return ChatMessageListResponse(
            content=[to_message_response(message, role) for message in page],
            has_previous=has_previous,
        )


def to_message_response(message: ChatMessage, viewer: ChatRole) -> ChatMessageResponse:
    if message.type == ChatMessageType.SYSTEM:
        content = render_system_chat(message.system_event, message.system_payload, viewer)
    else:
        content = message.content
    return ChatMessageResponse(
        id=message.id,
        room_id=message.room_id,
        seq=message.seq,
        type=message.type,
        sender_id=message.sender_id,
        content=content,
        system_event=message.system_event,
        created_at=message.created_at,
    )
