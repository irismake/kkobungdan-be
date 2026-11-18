"""관리자 웹 채팅 조회 (CHAT-REQ-002).

관리자는 모든 채팅방의 채팅을 볼 수 있다. 조회만 하고 채팅을 보내거나 참여자의 읽음 위치를 바꾸지 않는다.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import AppError, api_error
from app.models.chat import ChatMessage, ChatMessageType, ChatRole, ChatRoom
from app.models.offer import Offer
from app.models.user import User
from app.schemas.chat import AdminChatMessageListResponse, AdminChatMessageResponse, AdminChatRoomResponse
from app.services.chat.chat_message_service import page_messages
from app.services.chat.chat_room_service import display_name
from app.services.chat.system_chat import render_system_chat


class ChatAdminService:
    @staticmethod
    def list_rooms(db: Session, proposal_id: int) -> list[AdminChatRoomResponse]:
        """요청 하나의 채팅방(지원마다 1개)을 지원 순서대로."""
        rooms = db.query(ChatRoom).filter(ChatRoom.proposal_id == proposal_id).order_by(ChatRoom.id).all()
        if not rooms:
            return []
        user_ids = {room.orderer_id for room in rooms} | {room.runner_id for room in rooms}
        users = {user.id: user for user in db.query(User).filter(User.id.in_(user_ids)).all()}
        offer_statuses = dict(
            db.query(Offer.id, Offer.status).filter(Offer.id.in_([room.offer_id for room in rooms])).all()
        )
        return [
            AdminChatRoomResponse(
                id=room.id,
                proposal_id=room.proposal_id,
                offer_id=room.offer_id,
                orderer_id=room.orderer_id,
                orderer_name=display_name(users.get(room.orderer_id)),
                runner_id=room.runner_id,
                runner_name=display_name(users.get(room.runner_id)),
                status=room.status,
                status_reason=room.status_reason,
                offer_status=offer_statuses[room.offer_id],
                last_seq=room.last_seq,
                last_message_at=room.last_message_at,
                orderer_last_read_seq=room.orderer_last_read_seq,
                runner_last_read_seq=room.runner_last_read_seq,
                created_at=room.created_at,
            )
            for room in rooms
        ]

    @staticmethod
    def list_messages(
        db: Session, room_id: int, before_seq: int | None = None, after_seq: int | None = None
    ) -> AdminChatMessageListResponse:
        if before_seq is not None and after_seq is not None:
            raise api_error(AppError.VALIDATION_ERROR, "beforeSeq와 afterSeq는 함께 쓸 수 없습니다.")
        room = db.get(ChatRoom, room_id)
        if room is None:
            raise api_error(AppError.CHAT_ROOM_NOT_FOUND)
        page, has_previous = page_messages(db, room.id, before_seq, after_seq)
        return AdminChatMessageListResponse(
            content=[_to_admin_message(room, message) for message in page],
            has_previous=has_previous,
        )


def _to_admin_message(room: ChatRoom, message: ChatMessage) -> AdminChatMessageResponse:
    if message.type == ChatMessageType.SYSTEM:
        content = render_system_chat(message.system_event, message.system_payload, ChatRole.ORDERER)
        runner_content = render_system_chat(message.system_event, message.system_payload, ChatRole.RUNNER)
        sender_role = None
    else:
        content, runner_content = message.content, None
        sender_role = ChatRole.ORDERER if message.sender_id == room.orderer_id else ChatRole.RUNNER
    return AdminChatMessageResponse(
        id=message.id,
        room_id=message.room_id,
        seq=message.seq,
        type=message.type,
        sender_id=message.sender_id,
        sender_role=sender_role,
        content=content,
        runner_content=runner_content,
        system_event=message.system_event,
        created_at=message.created_at,
    )
