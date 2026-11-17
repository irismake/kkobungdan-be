"""다른 도메인 서비스가 부르는 채팅 입구 (docs/design-docs/chat-architecture.md "ChatLifecycle 호출 지점").

호출한 서비스의 트랜잭션 안에서 변경만 하고 커밋하지 않는다. 그래서 지원 등록과 채팅방 생성,
시스템 채팅, 첫 인사가 함께 성공하거나 함께 실패한다(CHAT-REQ-006, CHAT-REQ-023).
기존 EventBus는 핸들러 예외를 삼키므로 쓰지 않는다.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.time import utcnow_naive
from app.models.chat import ChatMessage, ChatMessageType, ChatRoom, ChatRoomStatus, SystemChatEvent
from app.models.offer import Offer
from app.models.proposal import Proposal


class ChatLifecycle:
    @staticmethod
    def on_offer_created(db: Session, offer: Offer, proposal: Proposal, greeting: str) -> ChatRoom:
        """지원 등록: 채팅방 생성 → 지원 등록 안내(시스템 채팅) → 꼬붕의 첫 인사(일반 채팅)."""
        room = ChatRoom(
            offer_id=offer.id,
            proposal_id=proposal.id,
            orderer_id=proposal.orderer_id,
            runner_id=offer.runner_id,
            status=ChatRoomStatus.ACTIVE,
            last_seq=0,
        )
        db.add(room)
        db.flush()

        ChatLifecycle._add_system_chat(db, room, SystemChatEvent.OFFER_CREATED, event_key=f"OFFER_CREATED:offer:{offer.id}")
        ChatLifecycle._add_greeting(db, room, offer.runner_id, greeting)
        return room

    @staticmethod
    def _add_system_chat(
        db: Session,
        room: ChatRoom,
        event: SystemChatEvent,
        *,
        event_key: str,
        payload: dict | None = None,
    ) -> ChatMessage:
        now = utcnow_naive()
        message = ChatMessage(
            room_id=room.id,
            seq=room.next_seq(),
            type=ChatMessageType.SYSTEM,
            system_event=event,
            system_payload=payload,
            system_event_key=event_key,
            created_at=now,
        )
        room.last_message_at = now
        db.add(message)
        return message

    @staticmethod
    def _add_greeting(db: Session, room: ChatRoom, runner_id: str, greeting: str) -> ChatMessage:
        now = utcnow_naive()
        message = ChatMessage(
            room_id=room.id,
            seq=room.next_seq(),
            type=ChatMessageType.USER,
            sender_id=runner_id,
            content=greeting,
            created_at=now,
        )
        room.last_message_at = now
        db.add(message)
        return message
