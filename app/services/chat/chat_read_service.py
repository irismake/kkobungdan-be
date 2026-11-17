"""읽음, 전체 읽음, 안읽음 수 (CHAT-REQ-010~013, docs/design-docs/chat-architecture.md "읽음과 안읽음").

읽음 위치는 한 문장의 조건부 UPDATE(`… WHERE last_read_seq < :seq`)로 올린다. 동시에 들어오거나
늦게 도착한 이전 요청이 있어도 뒤로 돌아가지 않고, 실제로 바뀐 경우에만 `version`이 오른다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.errors import AppError, api_error
from app.models.chat import ChatRole, ChatRoom
from app.schemas.chat import ChatReadAllResponse, ChatReadResponse, ChatUnreadRoomResponse, ChatUnreadSummaryResponse
from app.services.chat.chat_room_service import ChatRoomService
from app.services.chat.unread import last_read_seq, unread_count


@dataclass(frozen=True)
class ReadTarget:
    """전체 읽음 요청 시점에 정한 "이 채팅방은 이 순번까지 읽음"."""

    room_id: int
    role: ChatRole
    seq: int


class ChatReadService:
    @staticmethod
    def read(db: Session, room_id: int, user_id: str, seq: int) -> ChatReadResponse:
        """채팅방에 들어갔거나 보고 있는 중에 받은 채팅을 읽었다. 채팅방 상태·차단과 관계없다."""
        room, role = ChatRoomService.get_room_for_participant(db, room_id, user_id)
        if seq > room.last_seq:
            raise api_error(AppError.CHAT_READ_SEQ_INVALID)
        _advance(db, ReadTarget(room.id, role, seq))
        db.commit()
        db.refresh(room)
        return ChatReadResponse(
            room_id=room.id,
            last_read_seq=last_read_seq(room, role),
            unread_count=unread_count(db, room, user_id, role),
        )

    @staticmethod
    def read_all(db: Session, user_id: str) -> ChatReadAllResponse:
        """역할과 관계없이 내 모든 채팅방을 요청 시점의 마지막 채팅까지 읽는다."""
        ChatReadService.apply_read_targets(db, ChatReadService.read_all_targets(db, user_id))
        db.commit()
        return ChatReadAllResponse(total_unread_count=ChatReadService.unread_summary(db, user_id).total_unread_count)

    @staticmethod
    def read_all_targets(db: Session, user_id: str) -> list[ReadTarget]:
        """요청 시점에 읽을 것이 남은 내 채팅방과 그 마지막 순번."""
        targets: list[ReadTarget] = []
        for room in _rooms_with_unread_position(db, user_id):
            targets.append(ReadTarget(room.id, _role(room, user_id), room.last_seq))
        return targets

    @staticmethod
    def apply_read_targets(db: Session, targets: list[ReadTarget]) -> None:
        """정해 둔 위치까지 올린다. 그 사이 더 읽은 채팅방은 그대로 둔다(CHAT-REQ-012)."""
        for target in targets:
            _advance(db, target)

    @staticmethod
    def unread_summary(db: Session, user_id: str) -> ChatUnreadSummaryResponse:
        """채팅방별 안읽음 수와 합계. 닫힌 채팅방·차단한 상대의 채팅방도 포함한다(CHAT-REQ-011)."""
        rooms: list[ChatUnreadRoomResponse] = []
        for room in _rooms_with_unread_position(db, user_id):
            count = unread_count(db, room, user_id, _role(room, user_id))
            if count > 0:
                rooms.append(ChatUnreadRoomResponse(room_id=room.id, unread_count=count))
        return ChatUnreadSummaryResponse(total_unread_count=sum(item.unread_count for item in rooms), rooms=rooms)


def _role(room: ChatRoom, user_id: str) -> ChatRole:
    return ChatRole.ORDERER if room.orderer_id == user_id else ChatRole.RUNNER


def _rooms_with_unread_position(db: Session, user_id: str) -> list[ChatRoom]:
    """읽음 위치가 마지막 채팅보다 앞선 내 채팅방. 다 읽은 채팅방은 안읽음이 0이라 볼 필요가 없다."""
    return (
        db.query(ChatRoom)
        .filter(
            or_(
                (ChatRoom.orderer_id == user_id) & (ChatRoom.orderer_last_read_seq < ChatRoom.last_seq),
                (ChatRoom.runner_id == user_id) & (ChatRoom.runner_last_read_seq < ChatRoom.last_seq),
            )
        )
        .order_by(ChatRoom.id)
        .all()
    )


def _advance(db: Session, target: ReadTarget) -> None:
    column = ChatRoom.orderer_last_read_seq if target.role == ChatRole.ORDERER else ChatRoom.runner_last_read_seq
    (
        db.query(ChatRoom)
        .filter(ChatRoom.id == target.room_id, column < target.seq)
        .update({column: target.seq, ChatRoom.version: ChatRoom.version + 1}, synchronize_session=False)
    )
