"""Refund lifecycle orchestration shared by cancellation and dispute flows."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.mission import Mission
from app.models.proposal import Proposal
from app.models.refund import Refund, RefundReason, RefundStatus


class RefundService:
    """Create and locate the single refund attached to a paid proposal."""

    @staticmethod
    def create_pending(
        db: Session,
        proposal: Proposal,
        reason: RefundReason,
        reason_detail: str | None = None,
        mission: Mission | None = None,
    ) -> Refund:
        """입금이 확인된 요청의 환불. 이체만 남은 확정된 의무다."""
        return RefundService._create(db, proposal, reason, RefundStatus.PENDING, reason_detail, mission)

    @staticmethod
    def create_review(
        db: Session,
        proposal: Proposal,
        reason: RefundReason,
        reason_detail: str | None = None,
    ) -> Refund:
        """입금 확인 전 취소된 요청의 대조 대기 건.

        관리자 확인과 실제 입금 사이에는 시차가 있어서, 행님이 입금한 뒤 확인 전에 취소하면
        돈은 들어와 있는데 환불 대상이 남지 않는다. 관리자가 계좌 내역으로 판단할 때까지
        대기시킨다.
        """
        return RefundService._create(db, proposal, reason, RefundStatus.REVIEW, reason_detail, None)

    @staticmethod
    def _create(
        db: Session,
        proposal: Proposal,
        reason: RefundReason,
        status: RefundStatus,
        reason_detail: str | None,
        mission: Mission | None,
    ) -> Refund:
        existing = db.query(Refund).filter(Refund.proposal_id == proposal.id).first()
        if existing is not None:
            return existing

        refund = Refund(
            proposal_id=proposal.id,
            mission_id=mission.id if mission is not None else None,
            orderer_id=proposal.orderer_id,
            amount=proposal.errand_fee,
            reason=reason.value,
            reason_detail=reason_detail,
            status=status,
        )
        db.add(refund)
        db.flush()
        return refund

__all__ = ["RefundService"]
