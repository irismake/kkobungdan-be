"""Chat request and response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.chat import ChatMessageType, ChatRole, ChatRoomStatus, ChatRoomStatusReason, SystemChatEvent
from app.models.offer import OfferStatus
from app.models.proposal import ProposalStatus


class ChatRoomDetailResponse(BaseModel):
    """채팅방 상세. 상태 배지와 버튼은 요청·지원 상태로 그린다(CHAT-REQ-007)."""

    id: int
    proposal_id: int = Field(..., serialization_alias="proposalId")
    offer_id: int = Field(..., serialization_alias="offerId")
    proposal_title: str = Field(..., serialization_alias="proposalTitle", description="요청 제목")
    my_role: ChatRole = Field(..., serialization_alias="myRole", description="이 채팅방에서 나의 역할")
    partner_id: str = Field(..., serialization_alias="partnerId")
    partner_name: str = Field(..., serialization_alias="partnerName", description="상대 이름. 탈퇴했으면 '탈퇴한 사용자'")
    status: ChatRoomStatus = Field(..., description="채팅 전송 가능 여부를 나타내는 채팅방 상태")
    status_reason: ChatRoomStatusReason | None = Field(None, serialization_alias="statusReason")
    proposal_status: ProposalStatus = Field(..., serialization_alias="proposalStatus")
    offer_status: OfferStatus = Field(..., serialization_alias="offerStatus")
    last_seq: int = Field(..., serialization_alias="lastSeq", description="마지막 채팅 순번")
    my_last_read_seq: int = Field(..., serialization_alias="myLastReadSeq")
    partner_last_read_seq: int = Field(..., serialization_alias="partnerLastReadSeq")
    created_at: datetime = Field(..., serialization_alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class ChatMessageResponse(BaseModel):
    """채팅 1개. 시스템 채팅의 content는 보는 사람에 맞는 문구다."""

    id: int = Field(..., description="채팅 ID. 앱의 중복 제거 기준")
    room_id: int = Field(..., serialization_alias="roomId")
    seq: int = Field(..., description="채팅방 안의 저장 순서")
    type: ChatMessageType
    sender_id: str | None = Field(None, serialization_alias="senderId", description="보낸 사람. 시스템 채팅은 null")
    content: str
    system_event: SystemChatEvent | None = Field(None, serialization_alias="systemEvent")
    created_at: datetime = Field(..., serialization_alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class ChatMessageListResponse(BaseModel):
    """채팅 목록. 저장 순서(seq 오름차순)로 담는다."""

    content: list[ChatMessageResponse]
    has_previous: bool = Field(..., serialization_alias="hasPrevious", description="더 이전 채팅이 있는지")

    model_config = ConfigDict(populate_by_name=True)
