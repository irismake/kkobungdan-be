"""채팅방 조회와 참여 권한 확인 (CHAT-REQ-002)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import AppError, api_error
from app.models.chat import ChatRole, ChatRoom
from app.models.offer import Offer
from app.models.proposal import Proposal
from app.models.user import User
from app.schemas.chat import ChatRoomDetailResponse

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
            created_at=room.created_at,
        )


def display_name(user: User | None) -> str:
    """탈퇴했거나 이름이 지워진 사용자는 '탈퇴한 사용자'로 보여준다(CHAT-REQ-005)."""
    if user is None or not user.name:
        return WITHDRAWN_USER_NAME
    return user.name
