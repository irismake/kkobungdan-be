"""Chat request and response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.chat import ChatMessageType, ChatRole, ChatRoomStatus, ChatRoomStatusReason, SystemChatEvent
from app.models.offer import OfferStatus
from app.models.proposal import ProposalStatus
from app.services.chat.blocking import BlockStatus
from app.services.chat.content import validate_message_content


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
    version: int = Field(..., description="채팅방 상태·읽음 위치가 바뀔 때마다 1 증가. 실시간 이벤트와 순서를 맞출 때 쓴다")
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


class ChatMessageSendRequest(BaseModel):
    """채팅 전송. 시스템 채팅은 서버만 만들므로 채팅 유형 필드는 받지 않는다(CHAT-REQ-020)."""

    client_message_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        validation_alias="clientMessageId",
        description="앱이 채팅마다 만드는 전송 ID. 재시도할 때 같은 값을 보내면 한 번만 저장된다",
        examples=["9b2f3c1e-7a51-4c6d-9d1e-1f0a2b3c4d5e"],
    )
    content: str = Field(..., description="채팅 내용. 공백만 있으면 안 되고 화면 글자 기준 500자 이하", examples=["지금 어디세요?"])

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return validate_message_content(value)


class ChatLastMessageResponse(BaseModel):
    """채팅 목록에 보여줄 마지막 채팅. 시스템 채팅이면 보는 사람에 맞는 문구다."""

    id: int
    seq: int
    type: ChatMessageType
    sender_id: str | None = Field(None, serialization_alias="senderId")
    content: str
    created_at: datetime = Field(..., serialization_alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class ChatRoomListItemResponse(BaseModel):
    """채팅 목록 한 줄 (CHAT-REQ-014)."""

    id: int
    proposal_id: int = Field(..., serialization_alias="proposalId")
    offer_id: int = Field(..., serialization_alias="offerId")
    proposal_title: str = Field(..., serialization_alias="proposalTitle")
    my_role: ChatRole = Field(..., serialization_alias="myRole")
    partner_id: str = Field(..., serialization_alias="partnerId")
    partner_name: str = Field(..., serialization_alias="partnerName")
    last_message: ChatLastMessageResponse | None = Field(None, serialization_alias="lastMessage")
    last_message_at: datetime | None = Field(None, serialization_alias="lastMessageAt")
    unread_count: int = Field(..., serialization_alias="unreadCount")
    status: ChatRoomStatus
    status_reason: ChatRoomStatusReason | None = Field(None, serialization_alias="statusReason")
    proposal_status: ProposalStatus = Field(..., serialization_alias="proposalStatus")
    offer_status: OfferStatus = Field(..., serialization_alias="offerStatus")
    block_status: BlockStatus = Field(..., serialization_alias="blockStatus", description="차단 여부. 차단 구현 전에는 항상 NONE")
    created_at: datetime = Field(..., serialization_alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class ChatRoomListResponse(BaseModel):
    content: list[ChatRoomListItemResponse]
    next_cursor: str | None = Field(None, serialization_alias="nextCursor", description="다음 페이지 커서. 마지막 페이지면 null")

    model_config = ConfigDict(populate_by_name=True)


class ChatReadRequest(BaseModel):
    seq: int = Field(..., ge=1, description="읽은 마지막 채팅의 순번")

    model_config = ConfigDict(extra="forbid")


class ChatReadResponse(BaseModel):
    room_id: int = Field(..., serialization_alias="roomId")
    last_read_seq: int = Field(..., serialization_alias="lastReadSeq", description="처리 뒤 내 읽음 위치. 뒤로만 움직인다")
    unread_count: int = Field(..., serialization_alias="unreadCount")

    model_config = ConfigDict(populate_by_name=True)


class ChatUnreadRoomResponse(BaseModel):
    room_id: int = Field(..., serialization_alias="roomId")
    unread_count: int = Field(..., serialization_alias="unreadCount")

    model_config = ConfigDict(populate_by_name=True)


class ChatUnreadSummaryResponse(BaseModel):
    total_unread_count: int = Field(..., serialization_alias="totalUnreadCount", description="전체 채팅방 안읽음 합계")
    rooms: list[ChatUnreadRoomResponse] = Field(..., description="안읽음이 있는 채팅방만")

    model_config = ConfigDict(populate_by_name=True)


class ChatReadAllResponse(BaseModel):
    total_unread_count: int = Field(..., serialization_alias="totalUnreadCount", description="처리 뒤 남은 안읽음 합계")

    model_config = ConfigDict(populate_by_name=True)
