"""채팅방 조회와 참여 권한 확인 (CHAT-REQ-002)."""

from __future__ import annotations

import base64
from datetime import datetime

from sqlalchemy import and_, func, or_, tuple_
from sqlalchemy.orm import Session

from app.core.errors import AppError, api_error
from app.models.chat import ChatMessage, ChatRole, ChatRoom
from app.models.offer import Offer
from app.models.proposal import Proposal
from app.models.user import User
from app.schemas.chat import (
    ChatLastMessageResponse,
    ChatRoomDetailResponse,
    ChatRoomListItemResponse,
    ChatRoomListResponse,
)
from app.services.chat.blocking import block_status
from app.services.chat.system_chat import render_system_chat
from app.services.chat.unread import unread_count

WITHDRAWN_USER_NAME = "탈퇴한 사용자"


class ChatRoomService:
    @staticmethod
    def get_room_for_participant(db: Session, room_id: int, user_id: str) -> tuple[ChatRoom, ChatRole]:
        """참여자만 채팅방을 볼 수 있다. 없는 채팅방은 404, 참여자가 아니면 403."""
        room = db.get(ChatRoom, room_id)
        if room is None:
            raise api_error(AppError.CHAT_ROOM_NOT_FOUND)
        if user_id == room.orderer_id:
            return room, ChatRole.ORDERER
        if user_id == room.runner_id:
            return room, ChatRole.RUNNER
        raise api_error(AppError.FORBIDDEN)

    @staticmethod
    def get_detail(db: Session, room_id: int, user_id: str) -> ChatRoomDetailResponse:
        room, role = ChatRoomService.get_room_for_participant(db, room_id, user_id)
        proposal = db.get(Proposal, room.proposal_id)
        offer = db.get(Offer, room.offer_id)
        partner_id = room.runner_id if role == ChatRole.ORDERER else room.orderer_id
        partner = db.get(User, partner_id)
        my_last_read, partner_last_read = (
            (room.orderer_last_read_seq, room.runner_last_read_seq)
            if role == ChatRole.ORDERER
            else (room.runner_last_read_seq, room.orderer_last_read_seq)
        )
        return ChatRoomDetailResponse(
            id=room.id,
            proposal_id=room.proposal_id,
            offer_id=room.offer_id,
            proposal_title=proposal.title,
            my_role=role,
            partner_id=partner_id,
            partner_name=display_name(partner),
            status=room.status,
            status_reason=room.status_reason,
            proposal_status=proposal.status,
            offer_status=offer.status,
            last_seq=room.last_seq,
            my_last_read_seq=my_last_read,
            partner_last_read_seq=partner_last_read,
            version=room.version,
            created_at=room.created_at,
        )


def display_name(user: User | None) -> str:
    """탈퇴했거나 이름이 지워진 사용자는 '탈퇴한 사용자'로 보여준다(CHAT-REQ-005)."""
    if user is None or not user.name:
        return WITHDRAWN_USER_NAME
    return user.name


# ------------------------------------------------------------------ 채팅 목록 (CHAT-REQ-014)


DEFAULT_LIST_SIZE = 20


def _encode_cursor(sort_at: datetime, room_id: int) -> str:
    return base64.urlsafe_b64encode(f"{sort_at.isoformat()}|{room_id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        sort_text, room_id = base64.urlsafe_b64decode(cursor.encode()).decode().rsplit("|", 1)
        return datetime.fromisoformat(sort_text), int(room_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise api_error(AppError.VALIDATION_ERROR, "cursor 값이 올바르지 않습니다.") from exc


def list_rooms(db: Session, user_id: str, cursor: str | None, size: int = DEFAULT_LIST_SIZE) -> ChatRoomListResponse:
    """내가 참여한 채팅방(행님·꼬붕 역할 모두)을 마지막 채팅이 최신인 순서로 돌려준다.

    채팅이 없는 채팅방은 생성 시각으로 줄을 선다. 목록 조회는 읽음 상태를 바꾸지 않는다.
    """
    sort_at = func.coalesce(ChatRoom.last_message_at, ChatRoom.created_at)
    query = db.query(ChatRoom, sort_at.label("sort_at")).filter(
        or_(ChatRoom.orderer_id == user_id, ChatRoom.runner_id == user_id)
    )
    if cursor:
        cursor_at, cursor_id = _decode_cursor(cursor)
        query = query.filter(or_(sort_at < cursor_at, and_(sort_at == cursor_at, ChatRoom.id < cursor_id)))
    rows = query.order_by(sort_at.desc(), ChatRoom.id.desc()).limit(size + 1).all()
    page = rows[:size]
    next_cursor = _encode_cursor(page[-1][1], page[-1][0].id) if len(rows) > size and page else None

    rooms = [room for room, _ in page]
    proposals = {p.id: p for p in db.query(Proposal).filter(Proposal.id.in_([r.proposal_id for r in rooms])).all()} if rooms else {}
    offers = {o.id: o for o in db.query(Offer).filter(Offer.id.in_([r.offer_id for r in rooms])).all()} if rooms else {}
    partner_ids = [r.runner_id if r.orderer_id == user_id else r.orderer_id for r in rooms]
    partners = {u.id: u for u in db.query(User).filter(User.id.in_(partner_ids)).all()} if rooms else {}
    last_keys = [(r.id, r.last_seq) for r in rooms if r.last_seq]
    last_messages = (
        {m.room_id: m for m in db.query(ChatMessage).filter(tuple_(ChatMessage.room_id, ChatMessage.seq).in_(last_keys)).all()}
        if last_keys
        else {}
    )

    items = []
    for room in rooms:
        role = ChatRole.ORDERER if room.orderer_id == user_id else ChatRole.RUNNER
        partner_id = room.runner_id if role == ChatRole.ORDERER else room.orderer_id
        last = last_messages.get(room.id)
        items.append(
            ChatRoomListItemResponse(
                id=room.id,
                proposal_id=room.proposal_id,
                offer_id=room.offer_id,
                proposal_title=proposals[room.proposal_id].title,
                my_role=role,
                partner_id=partner_id,
                partner_name=display_name(partners.get(partner_id)),
                last_message=_last_message(last, role) if last else None,
                last_message_at=room.last_message_at,
                unread_count=unread_count(db, room, user_id, role),
                status=room.status,
                status_reason=room.status_reason,
                proposal_status=proposals[room.proposal_id].status,
                offer_status=offers[room.offer_id].status,
                block_status=block_status(db, user_id, partner_id),
                created_at=room.created_at,
            )
        )
    return ChatRoomListResponse(content=items, next_cursor=next_cursor)


def _last_message(message: ChatMessage, role: ChatRole) -> ChatLastMessageResponse:
    content = (
        render_system_chat(message.system_event, message.system_payload, role)
        if message.system_event is not None
        else message.content
    )
    return ChatLastMessageResponse(
        id=message.id,
        seq=message.seq,
        type=message.type,
        sender_id=message.sender_id,
        content=content,
        created_at=message.created_at,
    )
