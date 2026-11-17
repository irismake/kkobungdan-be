"""채팅 전송과 조회 (CHAT-REQ-003, 004, 019, 024)."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, api_error
from app.core.time import utcnow_naive
from app.models.chat import ChatMessage, ChatMessageType, ChatRole, ChatRoom, ChatRoomStatus
from app.schemas.chat import ChatMessageListResponse, ChatMessageResponse, ChatMessageSendRequest
from app.services.chat import chat_events
from app.services.chat.blocking import BlockStatus, block_status
from app.services.chat.chat_room_service import ChatRoomService
from app.services.chat.system_chat import render_system_chat

PAGE_SIZE = 30
AFTER_PAGE_SIZE = 100


class ChatMessageService:
    @staticmethod
    def list_messages(
        db: Session,
        room_id: int,
        user_id: str,
        before_seq: int | None = None,
        after_seq: int | None = None,
    ) -> ChatMessageListResponse:
        """채팅을 저장 순서(seq 오름차순)로 돌려준다.

        - 기본: 최근 30개
        - `beforeSeq`: 그보다 앞선 30개 (이전 채팅 더 보기)
        - `afterSeq`: 그 뒤의 채팅 (재연결 후 놓친 채팅 복구, 최대 100개)
        """
        if before_seq is not None and after_seq is not None:
            raise api_error(AppError.VALIDATION_ERROR, "beforeSeq와 afterSeq는 함께 쓸 수 없습니다.")
        room, role = ChatRoomService.get_room_for_participant(db, room_id, user_id)
        query = db.query(ChatMessage).filter(ChatMessage.room_id == room.id)
        if after_seq is not None:
            page = query.filter(ChatMessage.seq > after_seq).order_by(ChatMessage.seq).limit(AFTER_PAGE_SIZE).all()
        else:
            if before_seq is not None:
                query = query.filter(ChatMessage.seq < before_seq)
            rows = query.order_by(ChatMessage.seq.desc()).limit(PAGE_SIZE + 1).all()
            page = list(reversed(rows[:PAGE_SIZE]))
        has_previous = bool(page) and page[0].seq > 1
        return ChatMessageListResponse(
            content=[to_message_response(message, role) for message in page],
            has_previous=has_previous,
        )

    @staticmethod
    def send(db: Session, room_id: int, user_id: str, request: ChatMessageSendRequest) -> ChatMessageResponse:
        """일반 채팅을 저장한다.

        같은 사용자의 같은 전송 ID는 한 번만 저장하고, 재시도에는 처음 저장한 채팅으로 응답한다.
        내용이나 채팅방이 다르면 409. 순번은 채팅방 행을 잠근 상태에서 매긴다(CHAT-REQ-024).
        """
        room, role = ChatRoomService.get_room_for_participant(db, room_id, user_id)
        existing = _find_by_client_id(db, user_id, request.client_message_id)
        if existing is not None:
            return _replay(existing, room.id, request, role)

        room = (
            db.query(ChatRoom).filter(ChatRoom.id == room.id).populate_existing().with_for_update().one()
        )
        partner_id = room.runner_id if role == ChatRole.ORDERER else room.orderer_id
        if room.status != ChatRoomStatus.ACTIVE or block_status(db, user_id, partner_id) != BlockStatus.NONE:
            db.rollback()
            raise api_error(AppError.CHAT_ROOM_NOT_SENDABLE)

        now = utcnow_naive()
        message = ChatMessage(
            room_id=room.id,
            seq=room.next_seq(),
            type=ChatMessageType.USER,
            sender_id=user_id,
            content=request.content,
            client_message_id=request.client_message_id,
            created_at=now,
        )
        room.last_message_at = now
        _mark_read_before(room, role, message.seq)
        db.add(message)
        try:
            db.flush()
        except IntegrityError:
            # 같은 전송 ID가 동시에 들어와 다른 요청이 먼저 저장했다.
            db.rollback()
            existing = _find_by_client_id(db, user_id, request.client_message_id)
            if existing is None:
                raise
            return _replay(existing, room_id, request, role)
        chat_events.record_message_created(db, room, message)
        db.commit()
        db.refresh(message)
        return to_message_response(message, role)


def _find_by_client_id(db: Session, user_id: str, client_message_id: str) -> ChatMessage | None:
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.sender_id == user_id, ChatMessage.client_message_id == client_message_id)
        .one_or_none()
    )


def _replay(existing: ChatMessage, room_id: int, request: ChatMessageSendRequest, role: ChatRole) -> ChatMessageResponse:
    if existing.room_id != room_id or existing.content != request.content:
        raise api_error(AppError.CHAT_MESSAGE_ID_CONFLICT)
    return to_message_response(existing, role)


def _mark_read_before(room: ChatRoom, role: ChatRole, seq: int) -> None:
    """채팅을 보내면 그 채팅보다 먼저 저장된 채팅까지 읽은 것으로 본다(CHAT-REQ-010). 뒤로만 움직인다."""
    if role == ChatRole.ORDERER:
        if room.orderer_last_read_seq < seq - 1:
            room.orderer_last_read_seq = seq - 1
            room.version += 1
    elif room.runner_last_read_seq < seq - 1:
        room.runner_last_read_seq = seq - 1
        room.version += 1


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
