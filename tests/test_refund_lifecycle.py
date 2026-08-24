"""Refund lifecycle domain transitions that do not require a database."""

from __future__ import annotations

import pytest

from app.models.offer import Offer, OfferStatus
from app.models.mission import MissionStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.refund import Refund, RefundStatus


def test_removed_legacy_and_rejection_statuses_are_not_in_contract():
    assert "RESOLVED" not in {status.value for status in ProposalStatus}
    assert "RESOLVED" not in {status.value for status in OfferStatus}
    assert "REFUNDED" not in {status.value for status in MissionStatus}
    assert {status.value for status in RefundStatus} == {"PENDING", "COMPLETED"}


def test_completed_dispute_moves_proposal_and_offer_to_all_completed():
    proposal = Proposal(status=ProposalStatus.DISPUTED)
    offer = Offer(status=OfferStatus.DISPUTED)

    proposal.resolve_completed()
    offer.resolve_completed()

    assert proposal.status == ProposalStatus.ALL_COMPLETED
    assert offer.status == OfferStatus.ALL_COMPLETED
    assert proposal.resolved_at is not None
    assert offer.resolved_at is not None


def test_failed_dispute_moves_proposal_to_refund_and_offer_to_cancelled():
    proposal = Proposal(status=ProposalStatus.DISPUTED)
    offer = Offer(status=OfferStatus.DISPUTED)

    proposal.resolve_refund_pending()
    offer.resolve_cancelled()

    assert proposal.status == ProposalStatus.REFUND_PENDING
    assert offer.status == OfferStatus.CANCELLED


def test_refund_completion_moves_proposal_to_refunded():
    proposal = Proposal(status=ProposalStatus.REFUND_PENDING)
    refund = Refund(status=RefundStatus.PENDING.value)

    refund.complete(admin_id="admin", admin_note="이체 완료")
    proposal.mark_refunded()

    assert refund.status == RefundStatus.COMPLETED.value
    assert refund.processed_by_admin_id == "admin"
    assert refund.admin_note == "이체 완료"
    assert refund.processed_at is not None
    assert proposal.status == ProposalStatus.REFUNDED


@pytest.mark.parametrize(
    ("initial", "expected"),
    [
        (ProposalStatus.HOLDING, ProposalStatus.CANCELLED),
        (ProposalStatus.POSTED, ProposalStatus.REFUND_PENDING),
        (ProposalStatus.OFFERED, ProposalStatus.REFUND_PENDING),
    ],
)
def test_pre_match_cancel_distinguishes_unpaid_and_paid_proposals(initial, expected):
    proposal = Proposal(status=initial)

    proposal.cancel()

    assert proposal.status == expected


def test_processed_refund_cannot_be_processed_again():
    refund = Refund(status=RefundStatus.COMPLETED.value)

    with pytest.raises(ValueError, match="not pending"):
        refund.complete(admin_id=None, admin_note=None)
