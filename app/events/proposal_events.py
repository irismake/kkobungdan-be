from __future__ import annotations

from dataclasses import dataclass

from app.events.base import DomainEvent


@dataclass(frozen=True)
class PaymentExpiredProposalCancelledEvent(DomainEvent):
    """Raised when a proposal is auto-cancelled after the payment deadline passes."""

    proposal_id: int
    orderer_id: str
    proposal_title: str
