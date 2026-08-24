"""Proposal persistence model for errand requests."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Enum, Index, Integer, String

from app.core.database import Base
from app.core.errors import AppError, api_error
from app.core.time import utcnow_naive


class ProposalStatus(str, enum.Enum):
    """Proposal lifecycle status matching the Java API contract."""

    HOLDING = "HOLDING"
    POSTED = "POSTED"
    OFFERED = "OFFERED"
    MATCHED = "MATCHED"
    ORDER_COMPLETED = "ORDER_COMPLETED"
    ALL_COMPLETED = "ALL_COMPLETED"
    DISPUTED = "DISPUTED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"
    REPORTED = "REPORTED"
    CANCELLED = "CANCELLED"


class Proposal(Base):
    """Errand recruitment post created by an orderer."""

    __tablename__ = "proposals"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    orderer_id = Column(String(36), nullable=False, index=True)
    title = Column(String(50), nullable=False)
    content = Column(String(500), nullable=False)
    deadline = Column(DateTime(timezone=True), nullable=False)
    errand_fee = Column(Integer, nullable=False)
    status = Column(Enum(ProposalStatus), nullable=False, default=ProposalStatus.HOLDING, index=True)
    # 입금 확인 시 관리자가 입력한다. 수락된 지원이 생기기 전 단계라 지원에 둘 수 없다.
    open_chat_url = Column(String(500), nullable=True)
    admin_note = Column(String(500), nullable=True)

    # Kept for migration compatibility. These fields are not exposed by the current Java Proposal API.
    meeting_at = Column(DateTime(timezone=True), nullable=False)
    item_price = Column(Integer, nullable=False, default=0, server_default="0")
    deposit = Column(Integer, nullable=False, default=0, server_default="0")

    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive)
    matched_at = Column(DateTime(timezone=True), nullable=True)
    runner_confirmed_at = Column(DateTime(timezone=True), nullable=True)
    orderer_confirmed_at = Column(DateTime(timezone=True), nullable=True)
    disputed_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive, onupdate=utcnow_naive)

    __table_args__ = (Index("idx_proposals_orderer_id", "orderer_id"),)

    def can_receive_offers(self) -> bool:
        return self.status in {ProposalStatus.POSTED, ProposalStatus.OFFERED}

    def mark_as_offered(self) -> None:
        if self.status == ProposalStatus.POSTED:
            self.status = ProposalStatus.OFFERED

    def can_confirm_runner_completion(self) -> bool:
        return self.status in {ProposalStatus.MATCHED, ProposalStatus.ORDER_COMPLETED}

    def confirm_runner_completion(self) -> None:
        if not self.can_confirm_runner_completion():
            raise ValueError("Cannot confirm runner completion for proposal not in active execution status")
        self.runner_confirmed_at = utcnow_naive()

    def can_confirm_orderer_completion(self) -> bool:
        return self.status == ProposalStatus.MATCHED

    def confirm_orderer_completion(self) -> None:
        if not self.can_confirm_orderer_completion():
            raise ValueError("Cannot confirm orderer completion for proposal not in MATCHED status")
        self.status = ProposalStatus.ORDER_COMPLETED
        self.orderer_confirmed_at = utcnow_naive()

    def mark_all_completed(self) -> None:
        if self.status not in {ProposalStatus.ORDER_COMPLETED, ProposalStatus.MATCHED}:
            raise ValueError("Cannot mark all completed for proposal at this stage")
        self.status = ProposalStatus.ALL_COMPLETED

    def can_raise_dispute(self) -> bool:
        return self.status in {
            ProposalStatus.MATCHED,
            ProposalStatus.ORDER_COMPLETED,
        }

    def raise_dispute(self) -> None:
        if not self.can_raise_dispute():
            raise ValueError("Cannot raise dispute for proposal at this stage")
        self.status = ProposalStatus.DISPUTED
        self.disputed_at = utcnow_naive()

    def can_resolve(self) -> bool:
        return self.status == ProposalStatus.DISPUTED

    def resolve_completed(self) -> None:
        if not self.can_resolve():
            raise ValueError("Cannot resolve proposal not in DISPUTED status")
        self.status = ProposalStatus.ALL_COMPLETED
        self.resolved_at = utcnow_naive()

    def resolve_refund_pending(self) -> None:
        if not self.can_resolve():
            raise ValueError("Cannot resolve proposal not in DISPUTED status")
        self.status = ProposalStatus.REFUND_PENDING
        self.resolved_at = utcnow_naive()

    def mark_refund_pending(self, admin_note: str | None = None) -> None:
        if self.status not in {
            ProposalStatus.POSTED,
            ProposalStatus.OFFERED,
            ProposalStatus.MATCHED,
            ProposalStatus.ORDER_COMPLETED,
            ProposalStatus.DISPUTED,
        }:
            raise ValueError("Proposal cannot enter refund pending status")
        self.status = ProposalStatus.REFUND_PENDING
        if admin_note is not None:
            self.admin_note = admin_note

    def mark_refunded(self) -> None:
        if self.status != ProposalStatus.REFUND_PENDING:
            raise ValueError("Proposal is not awaiting refund")
        self.status = ProposalStatus.REFUNDED

    def admin_cancel(self, admin_note: str | None = None) -> None:
        """관리자 취소. 매칭 이후에도 취소할 수 있고 이미 취소된 건만 막는다."""
        if self.status in {ProposalStatus.CANCELLED, ProposalStatus.REFUNDED}:
            raise ValueError("Proposal is already cancelled")
        self.status = ProposalStatus.CANCELLED
        if admin_note is not None:
            self.admin_note = admin_note

    def cancel(self) -> None:
        if self.status not in {
            ProposalStatus.HOLDING,
            ProposalStatus.POSTED,
            ProposalStatus.OFFERED,
        }:
            raise ValueError("Cannot cancel proposal after matching")
        self.status = (
            ProposalStatus.CANCELLED
            if self.status == ProposalStatus.HOLDING
            else ProposalStatus.REFUND_PENDING
        )

    @classmethod
    def create_proposal(
        cls,
        orderer_id: str,
        title: str,
        content: str,
        deadline: datetime,
        errand_fee: int,
    ) -> "Proposal":
        validated_deadline = cls._validate_deadline(deadline)
        cls._validate_errand_fee(errand_fee)
        return cls(
            orderer_id=orderer_id,
            title=title,
            content=content,
            deadline=validated_deadline,
            errand_fee=errand_fee,
            status=ProposalStatus.HOLDING,
            meeting_at=validated_deadline,
            item_price=0,
            deposit=0,
        )

    def update_proposal(
        self,
        title: str,
        content: str,
        deadline: datetime,
        errand_fee: int,
    ) -> None:
        validated_deadline = self._validate_deadline(deadline)
        self._validate_errand_fee(errand_fee)
        self.title = title
        self.content = content
        self.deadline = validated_deadline
        self.errand_fee = errand_fee
        self.meeting_at = validated_deadline
        self.status = ProposalStatus.HOLDING

    @staticmethod
    def _validate_deadline(deadline: datetime) -> datetime:
        deadline_utc = deadline.astimezone(timezone.utc)
        if deadline_utc <= datetime.now(timezone.utc):
            raise api_error(AppError.PROPOSAL_DEADLINE_INVALID)
        return deadline_utc

    @staticmethod
    def _validate_errand_fee(errand_fee: int) -> None:
        if errand_fee < 1000:
            raise api_error(AppError.PROPOSAL_ERRAND_FEE_INVALID, "errandFee must be greater than or equal to 1000")
