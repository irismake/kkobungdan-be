"""채팅방 상태 변경 규칙 (CHAT-REQ-007, docs/design-docs/chat-architecture.md "요청·지원 상태와 함께 바뀌는 처리").

상태 전이는 `ACTIVE → INACTIVE → CLOSED`, `ACTIVE → CLOSED`만 허용한다. `CLOSED`는 다시 바뀌지 않는다(늦게 온 요청 무시).
"""

from __future__ import annotations

from enum import Enum

from app.models.chat import ChatRoomStatus, ChatRoomStatusReason


class RoomChange(str, Enum):
    """채팅방 상태를 바꾸는 사건."""

    MATCHED = "MATCHED"
    NOT_SELECTED = "NOT_SELECTED"
    OFFER_CANCELLED = "OFFER_CANCELLED"
    PROPOSAL_CANCELLED = "PROPOSAL_CANCELLED"
    ADMIN_CANCELLED = "ADMIN_CANCELLED"
    ORDERER_DISPUTED = "ORDERER_DISPUTED"
    RUNNER_DISPUTED = "RUNNER_DISPUTED"
    DISPUTE_COMPLETED = "DISPUTE_COMPLETED"
    DISPUTE_FAILED = "DISPUTE_FAILED"
    ALL_CONFIRMED = "ALL_CONFIRMED"


_TARGET: dict[RoomChange, tuple[ChatRoomStatus, ChatRoomStatusReason | None]] = {
    RoomChange.MATCHED: (ChatRoomStatus.ACTIVE, None),
    RoomChange.ORDERER_DISPUTED: (ChatRoomStatus.INACTIVE, ChatRoomStatusReason.ORDERER_DISPUTED),
    RoomChange.RUNNER_DISPUTED: (ChatRoomStatus.INACTIVE, ChatRoomStatusReason.RUNNER_DISPUTED),
    **{
        change: (ChatRoomStatus.CLOSED, ChatRoomStatusReason(change.value))
        for change in (
            RoomChange.NOT_SELECTED,
            RoomChange.OFFER_CANCELLED,
            RoomChange.PROPOSAL_CANCELLED,
            RoomChange.ADMIN_CANCELLED,
            RoomChange.DISPUTE_COMPLETED,
            RoomChange.DISPUTE_FAILED,
            RoomChange.ALL_CONFIRMED,
        )
    },
}

# 지금 상태 → 옮겨 갈 수 있는 상태
_ALLOWED: dict[ChatRoomStatus, set[ChatRoomStatus]] = {
    ChatRoomStatus.ACTIVE: {ChatRoomStatus.ACTIVE, ChatRoomStatus.INACTIVE, ChatRoomStatus.CLOSED},
    ChatRoomStatus.INACTIVE: {ChatRoomStatus.CLOSED},
    ChatRoomStatus.CLOSED: set(),
}


def next_room_state(
    status: ChatRoomStatus,
    reason: ChatRoomStatusReason | None,
    change: RoomChange,
) -> tuple[ChatRoomStatus, ChatRoomStatusReason | None]:
    """사건 뒤의 (상태, 이유). 허용되지 않는 전이면 지금 상태를 그대로 돌려준다."""
    target = _TARGET[change]
    if target[0] not in _ALLOWED[status]:
        return status, reason
    return target
