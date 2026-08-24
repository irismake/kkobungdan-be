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
            status=RefundStatus.PENDING.value,
        )
        db.add(refund)
        db.flush()
        return refund

__all__ = ["RefundService"]
