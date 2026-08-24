"""Dispute evidence model."""

from __future__ import annotations

import enum

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String, Text

from app.core.database import Base
from app.core.time import utcnow_naive


class DisputeProcessStatus(str, enum.Enum):
    """관리자의 분쟁 처리 상태. 요청·지원의 진행 상태와는 다른 축이다."""

    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class DisputeEvidence(Base):
    """Reason recorded when an accepted offer execution enters dispute."""

    __tablename__ = "dispute_evidences"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    proposal_id = Column(BigInteger, nullable=False, index=True)
    offer_id = Column(BigInteger, nullable=False, index=True)
    mission_id = Column(BigInteger, ForeignKey("missions.id", name="fk_dispute_evidences_mission_id"), nullable=False)
    actor_id = Column(String(36), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    survey_question_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive)

    status = Column(
        String(20),
        nullable=False,
        default=DisputeProcessStatus.PENDING.value,
        server_default=DisputeProcessStatus.PENDING.value,
        index=True,
    )
    admin_note = Column(String(500), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_admin_id = Column(String(36), nullable=True)

    __table_args__ = (
        Index("idx_dispute_evidences_survey_question_id", "survey_question_id"),
        Index("idx_dispute_evidences_mission_id", "mission_id"),
    )

    def is_pending(self) -> bool:
        return self.status == DisputeProcessStatus.PENDING.value

    def mark_resolved(self, admin_id: str | None, admin_note: str | None) -> None:
        self.status = DisputeProcessStatus.RESOLVED.value
        self.resolved_at = utcnow_naive()
        self.resolved_by_admin_id = admin_id
        self.admin_note = admin_note

    def mark_rejected(self, admin_id: str | None, admin_note: str | None) -> None:
        self.status = DisputeProcessStatus.REJECTED.value
        self.resolved_at = utcnow_naive()
        self.resolved_by_admin_id = admin_id
        self.admin_note = admin_note


__all__ = ["DisputeEvidence", "DisputeProcessStatus"]
