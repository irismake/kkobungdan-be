"""Refund persistence model shared by pre-match cancellations and failed missions."""

from __future__ import annotations

import enum

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, Text, UniqueConstraint

from app.core.database import Base
from app.core.time import utcnow_naive
from app.models.enum_type import enum_column


class RefundReason(str, enum.Enum):
    """Business event that made an orderer's confirmed payment refundable."""

    USER_CANCELLED = "USER_CANCELLED"
    ADMIN_CANCELLED = "ADMIN_CANCELLED"
    DISPUTE_FAILED = "DISPUTE_FAILED"
    PAYMENT_EXPIRED = "PAYMENT_EXPIRED"


class RefundStatus(str, enum.Enum):
    """Manual transfer processing status.

    ``REVIEW`` precedes the refund obligation. The orderer cancelled while the payment was
    still unconfirmed, so an admin has to reconcile the bank statement before deciding.
    """

    REVIEW = "REVIEW"
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    VOIDED = "VOIDED"


class Refund(Base):
    """One full refund for a proposal whose payment was already confirmed."""

    __tablename__ = "refunds"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    proposal_id = Column(BigInteger, nullable=False)
    mission_id = Column(BigInteger, nullable=True)
    orderer_id = Column(String(36), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    reason = Column(enum_column(RefundReason, 30, table="refunds", column="reason"), nullable=False)
    reason_detail = Column(Text, nullable=True)
    status = Column(enum_column(RefundStatus, 20, table="refunds", column="status"), nullable=False, default=RefundStatus.PENDING, index=True)
    requested_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    processed_by_admin_id = Column(String(36), nullable=True)
    admin_note = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive, onupdate=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("proposal_id", name="uk_refunds_proposal_id"),
        UniqueConstraint("mission_id", name="uk_refunds_mission_id"),
        Index("idx_refunds_status_requested", "status", "requested_at", "id"),
    )

    def confirm_deposit(self) -> None:
        """대조 결과 입금이 확인되어 환불 의무가 확정된다."""
        if self.status != RefundStatus.REVIEW:
            raise ValueError("Refund is not awaiting deposit review")
        self.status = RefundStatus.PENDING

    def void(self, admin_id: str | None, admin_note: str) -> None:
        """대조 결과 입금이 없어 환불 없이 종결한다. 반려가 아니라 받은 돈이 없다는 뜻이다."""
        if self.status != RefundStatus.REVIEW:
            raise ValueError("Refund is not awaiting deposit review")
        self.status = RefundStatus.VOIDED
        self.processed_at = utcnow_naive()
        self.processed_by_admin_id = admin_id
        self.admin_note = admin_note

    def complete(self, admin_id: str | None, admin_note: str | None) -> None:
        if self.status != RefundStatus.PENDING:
            raise ValueError("Refund is not pending")
        self.status = RefundStatus.COMPLETED
        self.processed_at = utcnow_naive()
        self.processed_by_admin_id = admin_id
        self.admin_note = admin_note

__all__ = ["Refund", "RefundReason", "RefundStatus"]
