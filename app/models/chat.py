"""Chat room and chat message models (docs/design-docs/chat-architecture.md)."""

from __future__ import annotations

import enum

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, String, Text, UniqueConstraint

from app.core.database import Base
from app.core.time import utcnow_naive
from app.models.enum_type import enum_column


class ChatRoomStatus(str, enum.Enum):
    """채팅 전송 가능 여부. 임무 단계는 요청·지원 상태가 표현한다."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    CLOSED = "CLOSED"


class ChatRoomStatusReason(str, enum.Enum):
    """같은 상태 안에서 앱에 보여줄 이유 (chat-requirements.md 상태 이유 표)."""

    ORDERER_DISPUTED = "ORDERER_DISPUTED"
    RUNNER_DISPUTED = "RUNNER_DISPUTED"
    NOT_SELECTED = "NOT_SELECTED"
    OFFER_CANCELLED = "OFFER_CANCELLED"
    PROPOSAL_CANCELLED = "PROPOSAL_CANCELLED"
    ADMIN_CANCELLED = "ADMIN_CANCELLED"
    ALL_CONFIRMED = "ALL_CONFIRMED"
    DISPUTE_COMPLETED = "DISPUTE_COMPLETED"
    DISPUTE_FAILED = "DISPUTE_FAILED"


class ChatRole(str, enum.Enum):
    """채팅방 안에서의 역할. 같은 사용자도 채팅방마다 역할이 다를 수 있다."""

    ORDERER = "ORDERER"
    RUNNER = "RUNNER"


class ChatMessageType(str, enum.Enum):
    USER = "USER"
    SYSTEM = "SYSTEM"


class SystemChatEvent(str, enum.Enum):
    """시스템 채팅을 만든 사건 (CHAT-REQ-021). 문구는 조회할 때 보는 사람에 맞춰 만든다."""

    OFFER_CREATED = "OFFER_CREATED"
    MATCHED = "MATCHED"
    NOT_SELECTED = "NOT_SELECTED"
    OFFER_CANCELLED = "OFFER_CANCELLED"
    RUNNER_COMPLETED = "RUNNER_COMPLETED"
    ORDERER_CONFIRMED = "ORDERER_CONFIRMED"
    ALL_CONFIRMED = "ALL_CONFIRMED"
    DISPUTE_RAISED = "DISPUTE_RAISED"
    DISPUTE_COMPLETED = "DISPUTE_COMPLETED"
    DISPUTE_FAILED = "DISPUTE_FAILED"
    PROPOSAL_CANCELLED = "PROPOSAL_CANCELLED"
    ADMIN_CANCELLED_AFTER_MATCH = "ADMIN_CANCELLED_AFTER_MATCH"
    PAYOUT_COMPLETED = "PAYOUT_COMPLETED"
    REFUND_COMPLETED = "REFUND_COMPLETED"


class ChatRoom(Base):
    """지원(Offer) 1건당 하나인 행님–꼬붕 1:1 채팅방."""

    __tablename__ = "chat_rooms"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    offer_id = Column(BigInteger, nullable=False)
    proposal_id = Column(BigInteger, nullable=False, index=True)
    orderer_id = Column(String(36), nullable=False)
    runner_id = Column(String(36), nullable=False)
    status = Column(
        enum_column(ChatRoomStatus, 10, table="chat_rooms", column="status"),
        nullable=False,
        default=ChatRoomStatus.ACTIVE,
    )
    status_reason = Column(
        enum_column(ChatRoomStatusReason, 30, table="chat_rooms", column="status_reason"),
        nullable=True,
    )
    last_seq = Column(BigInteger, nullable=False, default=0, server_default="0")
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    orderer_last_read_seq = Column(BigInteger, nullable=False, default=0, server_default="0")
    runner_last_read_seq = Column(BigInteger, nullable=False, default=0, server_default="0")
    version = Column(BigInteger, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive, onupdate=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("offer_id", name="uk_chat_rooms_offer_id"),
        Index("idx_chat_rooms_orderer_last_message", "orderer_id", "last_message_at"),
        Index("idx_chat_rooms_runner_last_message", "runner_id", "last_message_at"),
    )

    def is_participant(self, user_id: str) -> bool:
        return user_id in (self.orderer_id, self.runner_id)

    def next_seq(self) -> int:
        """다음 채팅 순번을 매긴다. 호출한 쪽이 이 행을 잠근 상태여야 한다(CHAT-REQ-024)."""
        self.last_seq = (self.last_seq or 0) + 1
        return self.last_seq


class ChatMessage(Base):
    """채팅방의 일반 채팅과 시스템 채팅. `seq`가 채팅방 안의 저장 순서다."""

    __tablename__ = "chat_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    room_id = Column(BigInteger, nullable=False)
    seq = Column(BigInteger, nullable=False)
    type = Column(enum_column(ChatMessageType, 10, table="chat_messages", column="type"), nullable=False)
    sender_id = Column(String(36), nullable=True)
    content = Column(Text, nullable=True)
    system_event = Column(
        enum_column(SystemChatEvent, 40, table="chat_messages", column="system_event"),
        nullable=True,
    )
    system_payload = Column(JSON, nullable=True)
    system_event_key = Column(String(100), nullable=True)
    client_message_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("room_id", "seq", name="uk_chat_messages_room_seq"),
        UniqueConstraint("room_id", "system_event_key", name="uk_chat_messages_room_system_event_key"),
        UniqueConstraint("sender_id", "client_message_id", name="uk_chat_messages_sender_client_message_id"),
    )
