"""다른 도메인 서비스가 부르는 채팅 입구 (docs/design-docs/chat-architecture.md "ChatLifecycle 호출 지점").

호출한 서비스의 트랜잭션 안에서 변경만 하고 커밋하지 않는다. 그래서 요청·지원 상태 변경과 채팅방 상태,
시스템 채팅, 채팅 이벤트 기록이 함께 성공하거나 함께 실패한다(CHAT-REQ-006, CHAT-REQ-023, CHAT-REQ-026).
기존 EventBus는 핸들러 예외를 삼키므로 쓰지 않는다.

- 채팅방 행을 잠근 뒤 상태를 바꾸고 시스템 채팅을 저장한다. 순번(`seq`)도 이 잠금 안에서 매긴다.
- `CLOSED` 채팅방은 상태도 바꾸지 않고 상태 안내도 남기지 않는다(늦게 온 요청 무시).
  돈 안내(수행비 입금·환불 완료)는 닫힌 채팅방에도 남긴다(CHAT-REQ-022).
- 같은 사건은 `system_event_key`로 한 번만 저장한다(CHAT-REQ-024). 같은 사건이 다시 들어와도 결과가 같다.
- 채팅 기능 이전에 만들어진 지원에는 채팅방이 없을 수 있다. 그때는 아무것도 하지 않는다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.time import utcnow_naive
from app.models.chat import ChatMessage, ChatMessageType, ChatRole, ChatRoom, ChatRoomStatus, SystemChatEvent
from app.models.mission import Mission
from app.models.offer import Offer
from app.models.proposal import Proposal
from app.models.refund import Refund
from app.services.chat import chat_events
from app.services.chat.room_status import RoomChange, next_room_state


class ChatLifecycle:
    # ------------------------------------------------------------------ 지원·매칭

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

        ChatLifecycle._add_system_chat(db, room, SystemChatEvent.OFFER_CREATED)
        ChatLifecycle._add_greeting(db, room, offer.runner_id, greeting)
        return room

    @staticmethod
    def on_offer_accepted(db: Session, offer: Offer) -> None:
        """매칭: 선택된 지원의 채팅방은 ACTIVE로 두고 매칭 안내, 나머지 열린 채팅방은 미선정으로 닫는다."""
        for room in ChatLifecycle._lock_rooms_of_proposal(db, offer.proposal_id):
            if room.offer_id == offer.id:
                ChatLifecycle._change(db, room, RoomChange.MATCHED, SystemChatEvent.MATCHED)
            else:
                ChatLifecycle._change(db, room, RoomChange.NOT_SELECTED, SystemChatEvent.NOT_SELECTED)

    @staticmethod
    def on_offer_cancelled(db: Session, offer: Offer) -> None:
        """꼬붕의 지원 취소(직접 취소, 탈퇴로 자동 취소)."""
        room = ChatLifecycle._lock_room_of_offer(db, offer.id)
        if room is not None:
            ChatLifecycle._change(db, room, RoomChange.OFFER_CANCELLED, SystemChatEvent.OFFER_CANCELLED)

    # ------------------------------------------------------------------ 요청 취소

    @staticmethod
    def on_proposal_cancelled(db: Session, proposal_id: int) -> None:
        """행님의 매칭 전 요청 취소: 열린 채팅방을 모두 닫는다."""
        for room in ChatLifecycle._lock_rooms_of_proposal(db, proposal_id):
            ChatLifecycle._change(db, room, RoomChange.PROPOSAL_CANCELLED, SystemChatEvent.PROPOSAL_CANCELLED)

    @staticmethod
    def on_admin_cancelled(db: Session, proposal_id: int, *, after_match: bool) -> None:
        """관리자 취소: 열린 채팅방을 닫는다. 임무가 있으면 매칭 후 문구, 없으면 요청 취소 문구."""
        event = SystemChatEvent.ADMIN_CANCELLED_AFTER_MATCH if after_match else SystemChatEvent.PROPOSAL_CANCELLED
        for room in ChatLifecycle._lock_rooms_of_proposal(db, proposal_id):
            ChatLifecycle._change(db, room, RoomChange.ADMIN_CANCELLED, event)

    @staticmethod
    def on_report_accepted(db: Session, proposal_id: int) -> None:
        """게시글 신고 승인: 대기 지원의 채팅방을 닫는다. 시스템 채팅은 남기지 않는다."""
        for room in ChatLifecycle._lock_rooms_of_proposal(db, proposal_id):
            ChatLifecycle._change(db, room, RoomChange.ADMIN_CANCELLED, None)

    # ------------------------------------------------------------------ 임무 완료

    @staticmethod
    def on_runner_completed(db: Session, offer: Offer, *, all_confirmed: bool) -> None:
        ChatLifecycle._on_completion(db, offer, SystemChatEvent.RUNNER_COMPLETED, all_confirmed)

    @staticmethod
    def on_orderer_confirmed(db: Session, offer: Offer, *, all_confirmed: bool) -> None:
        ChatLifecycle._on_completion(db, offer, SystemChatEvent.ORDERER_CONFIRMED, all_confirmed)

    @staticmethod
    def _on_completion(db: Session, offer: Offer, one_side: SystemChatEvent, all_confirmed: bool) -> None:
        """한쪽만 완료하면 안내만, 양쪽이 모두 완료하면 양측 완료 안내만 남기고 닫는다."""
        room = ChatLifecycle._lock_room_of_offer(db, offer.id)
        if room is None:
            return
        if all_confirmed:
            ChatLifecycle._change(db, room, RoomChange.ALL_CONFIRMED, SystemChatEvent.ALL_CONFIRMED)
        elif room.status == ChatRoomStatus.ACTIVE:
            ChatLifecycle._add_system_chat(db, room, one_side)

    # ------------------------------------------------------------------ 분쟁

    @staticmethod
    def on_dispute_raised(db: Session, offer: Offer, *, raised_by: ChatRole) -> None:
        room = ChatLifecycle._lock_room_of_offer(db, offer.id)
        if room is None:
            return
        change = RoomChange.ORDERER_DISPUTED if raised_by == ChatRole.ORDERER else RoomChange.RUNNER_DISPUTED
        ChatLifecycle._change(db, room, change, SystemChatEvent.DISPUTE_RAISED, payload={"raisedBy": raised_by.value})

    @staticmethod
    def on_dispute_resolved(db: Session, offer_id: int, *, completed: bool) -> None:
        room = ChatLifecycle._lock_room_of_offer(db, offer_id)
        if room is None:
            return
        if completed:
            ChatLifecycle._change(db, room, RoomChange.DISPUTE_COMPLETED, SystemChatEvent.DISPUTE_COMPLETED)
        else:
            ChatLifecycle._change(db, room, RoomChange.DISPUTE_FAILED, SystemChatEvent.DISPUTE_FAILED)

    # ------------------------------------------------------------------ 돈 안내 (닫힌 채팅방에도 남긴다)

    @staticmethod
    def on_payout_completed(db: Session, mission: Mission) -> None:
        """수행비 입금 완료. 같은 임무는 한 번만 안내한다."""
        room = ChatLifecycle._lock_room_of_offer(db, mission.offer_id)
        if room is None:
            return
        ChatLifecycle._add_system_chat(
            db,
            room,
            SystemChatEvent.PAYOUT_COMPLETED,
            event_key=f"PAYOUT_COMPLETED:mission:{mission.id}",
            payload={"amount": mission.errand_fee},
        )

    @staticmethod
    def on_refund_completed(db: Session, refund: Refund) -> None:
        """환불 완료. 매칭 후(임무가 있는) 환불만 그 임무의 채팅방에 안내한다."""
        if refund.mission_id is None:
            return
        mission = db.get(Mission, refund.mission_id)
        if mission is None:
            return
        room = ChatLifecycle._lock_room_of_offer(db, mission.offer_id)
        if room is None:
            return
        ChatLifecycle._add_system_chat(
            db, room, SystemChatEvent.REFUND_COMPLETED, event_key=f"REFUND_COMPLETED:refund:{refund.id}"
        )

    # ------------------------------------------------------------------ 내부

    @staticmethod
    def _lock_room_of_offer(db: Session, offer_id: int) -> ChatRoom | None:
        return (
            db.query(ChatRoom)
            .filter(ChatRoom.offer_id == offer_id)
            .populate_existing()
            .with_for_update()
            .one_or_none()
        )

    @staticmethod
    def _lock_rooms_of_proposal(db: Session, proposal_id: int) -> list[ChatRoom]:
        # 잠금 순서를 id로 고정해 서로 다른 요청이 같은 채팅방들을 잠글 때 교착을 막는다.
        return (
            db.query(ChatRoom)
            .filter(ChatRoom.proposal_id == proposal_id)
            .order_by(ChatRoom.id)
            .populate_existing()
            .with_for_update()
            .all()
        )

    @staticmethod
    def _change(
        db: Session,
        room: ChatRoom,
        change: RoomChange,
        event: SystemChatEvent | None,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """채팅방 상태를 바꾸고 안내를 남긴다. 닫힌 채팅방이나 허용되지 않는 전이는 무시한다."""
        if room.status == ChatRoomStatus.CLOSED:
            return
        new_status, new_reason = next_room_state(room.status, room.status_reason, change)
        unchanged = (new_status, new_reason) == (room.status, room.status_reason)
        # 매칭은 ACTIVE를 그대로 두는 것이 정상이라 상태가 같아도 안내를 남긴다.
        if unchanged and change != RoomChange.MATCHED:
            return
        if not unchanged:
            room.status = new_status
            room.status_reason = new_reason
            room.version += 1
        if event is not None:
            ChatLifecycle._add_system_chat(db, room, event, payload=payload)

    @staticmethod
    def _add_system_chat(
        db: Session,
        room: ChatRoom,
        event: SystemChatEvent,
        *,
        event_key: str | None = None,
        payload: dict | None = None,
    ) -> ChatMessage:
        """시스템 채팅을 저장한다. 같은 사건 키가 이미 있으면 그 채팅을 돌려준다."""
        event_key = event_key or f"{event.value}:offer:{room.offer_id}"
        existing = (
            db.query(ChatMessage)
            .filter(ChatMessage.room_id == room.id, ChatMessage.system_event_key == event_key)
            .one_or_none()
        )
        if existing is not None:
            return existing

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
        db.flush()
        chat_events.record_message_created(db, room, message)
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
        db.flush()
        chat_events.record_message_created(db, room, message)
        return message
