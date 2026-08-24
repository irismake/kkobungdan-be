"""Mission persistence model for accepted offer execution."""

from __future__ import annotations

import enum

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, UniqueConstraint

from app.core.database import Base
from app.core.time import utcnow_naive


class MissionStatus(str, enum.Enum):
    """Mission lifecycle status tracked for the admin console."""

    STARTED = "STARTED"
    DISPUTED = "DISPUTED"
    COMPLETED = "COMPLETED"
    PAID = "PAID"
    FAILED = "FAILED"


class PayoutStatus(str, enum.Enum):
    """수행비 지급 처리 상태. 미션 필드에서 파생하며 별도 컬럼이 없다."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class MissionResolution(str, enum.Enum):
    """Admin verdict recorded when a disputed mission is resolved."""

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


#: 지급 대기 상태. 수행비 지급을 기록할 수 있는 유일한 상태다.
SETTLEABLE_STATUS = MissionStatus.COMPLETED
#: 더 이상 전이하지 않는 종료 상태.
TERMINAL_STATUSES = (MissionStatus.PAID, MissionStatus.FAILED)


class Mission(Base):
    """Execution unit created when an orderer accepts a runner's offer.

    앱에는 노출하지 않고 관리자 웹에서만 사용한다. 상태는 요청과 지원의 상태에서 파생하되
    관리자 목록을 상태로 필터링해야 하므로 컬럼으로 실체화해 저장한다.
    """

    __tablename__ = "missions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    proposal_id = Column(BigInteger, nullable=False)
    offer_id = Column(BigInteger, nullable=False)
    orderer_id = Column(String(36), nullable=False, index=True)
    runner_id = Column(String(36), nullable=False, index=True)
    status = Column(String(20), nullable=False, default=MissionStatus.STARTED.value, index=True)
    errand_fee = Column(Integer, nullable=False)

    started_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive)
    disputed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)

    resolution = Column(String(20), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_admin_id = Column(String(36), nullable=True)

    # 지급 여부는 별도 boolean 없이 시각 컬럼의 null 여부로 판정한다.
    settlement_paid_at = Column(DateTime(timezone=True), nullable=True)
    settlement_paid_by_admin_id = Column(String(36), nullable=True)
    # 반려는 기록만 남기고 미션 상태를 되돌리지 않는다.
    settlement_rejected_at = Column(DateTime(timezone=True), nullable=True)
    settlement_rejected_by_admin_id = Column(String(36), nullable=True)
    payout_memo = Column(String(200), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive, onupdate=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("proposal_id", name="uk_missions_proposal_id"),
        UniqueConstraint("offer_id", name="uk_missions_offer_id"),
        Index("idx_missions_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Mission(id={self.id}, offer_id={self.offer_id}, status={self.status})>"

    @property
    def settlement_paid(self) -> bool:
        """꼬붕에게 수행비가 입금됐는지 여부."""
        return self.settlement_paid_at is not None

    @property
    def settlement_status(self) -> PayoutStatus:
        """수행비 지급 관점에서 본 처리 상태."""
        if self.settlement_paid:
            return PayoutStatus.COMPLETED
        if self.settlement_rejected_at is not None:
            return PayoutStatus.REJECTED
        return PayoutStatus.PENDING

    @classmethod
    def start(cls, proposal_id: int, offer_id: int, orderer_id: str, runner_id: str, errand_fee: int) -> "Mission":
        now = utcnow_naive()
        return cls(
            proposal_id=proposal_id,
            offer_id=offer_id,
            orderer_id=orderer_id,
            runner_id=runner_id,
            errand_fee=errand_fee,
            status=MissionStatus.STARTED.value,
            started_at=now,
        )

    def is_terminal(self) -> bool:
        return self.status in {status.value for status in TERMINAL_STATUSES}

    def mark_disputed(self) -> None:
        if self.status != MissionStatus.STARTED.value:
            return
        self.status = MissionStatus.DISPUTED.value
        self.disputed_at = utcnow_naive()

    def mark_completed(self) -> None:
        if self.status not in {MissionStatus.STARTED.value, MissionStatus.DISPUTED.value}:
            return
        self.status = MissionStatus.COMPLETED.value
        self.completed_at = utcnow_naive()

    def mark_failed(self) -> None:
        if self.status not in {MissionStatus.STARTED.value, MissionStatus.DISPUTED.value}:
            return
        self.status = MissionStatus.FAILED.value
        self.failed_at = utcnow_naive()

    def can_resolve(self) -> bool:
        return self.status == MissionStatus.DISPUTED.value

    def can_record_settlement(self) -> bool:
        return self.status == SETTLEABLE_STATUS.value and not self.settlement_paid

    def can_reject_settlement(self) -> bool:
        return self.can_record_settlement() and self.settlement_rejected_at is None

    def reject_settlement(self, admin_id: str | None, memo: str | None) -> None:
        """지급을 반려한다. 미션 상태는 COMPLETED 그대로 둔다."""
        self.settlement_rejected_at = utcnow_naive()
        self.settlement_rejected_by_admin_id = admin_id
        self.payout_memo = memo

    def record_settlement(self, admin_id: str | None, memo: str | None) -> None:
        self.settlement_paid_at = utcnow_naive()
        self.settlement_paid_by_admin_id = admin_id
        self.payout_memo = memo
        self.status = MissionStatus.PAID.value

__all__ = [
    "Mission",
    "PayoutStatus",
    "MissionResolution",
    "MissionStatus",
    "SETTLEABLE_STATUS",
    "TERMINAL_STATUSES",
]
