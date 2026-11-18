"""Admin console commands. 관리자 웹에서 상태를 바꾸는 처리를 담당한다."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import AppError, api_error
from app.models.dispute_evidence import DisputeEvidence
from app.models.mission import Mission, MissionResolution, MissionStatus
from app.models.offer import Offer, OfferStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.notification import NotificationType
from app.models.refund import Refund, RefundReason, RefundStatus
from app.schemas.admin import (
    AdminDisputeDetailResponse,
    AdminPayoutDetailResponse,
    AdminProposalDetailResponse,
    AdminRefundDetailResponse,
)
from app.services.admin.admin_query_service import AdminQueryService
from app.services.chat.chat_lifecycle import ChatLifecycle
from app.services.locking import lock_mission, lock_mission_of_offer, lock_offer, lock_proposal
from app.services.mission.mission_service import MissionService
from app.services.refund.refund_service import RefundService
from app.services.notification.proposal_notice import create_before_offer_notice


#: 관리자 취소 시 함께 취소하는 지원 상태. 이미 종료된 지원은 건드리지 않는다.
CANCELLABLE_OFFER_STATUSES = (
    OfferStatus.WAITING,
    OfferStatus.ACCEPTED,
    OfferStatus.RUNNER_COMPLETED,
    OfferStatus.DISPUTED,
)

CANCELLABLE_PROPOSAL_STATUSES = (
    ProposalStatus.HOLDING,
    ProposalStatus.POSTED,
    ProposalStatus.OFFERED,
    ProposalStatus.MATCHED,
    ProposalStatus.ORDER_COMPLETED,
)


class AdminCommandService:
    """관리자 처리 서비스."""

    # ---------------------------------------------------------------- 요청

    @staticmethod
    def cancel_proposal(
        db: Session,
        proposal_id: int,
        admin_note: str | None,
    ) -> AdminProposalDetailResponse:
        """요청을 취소하고 연결된 지원과 미션을 함께 종결한다."""
        proposal = lock_proposal(db, proposal_id)
        if proposal is None:
            raise api_error(AppError.PROPOSAL_NOT_FOUND, f"id: {proposal_id}")
        if proposal.status not in CANCELLABLE_PROPOSAL_STATUSES:
            raise api_error(AppError.PROPOSAL_NOT_CANCELLABLE, f"status: {proposal.status.value}")

        mission = (
            db.query(Mission).filter(Mission.proposal_id == proposal.id).populate_existing().with_for_update().first()
        )
        if mission is not None and mission.status not in {
            MissionStatus.STARTED,
            MissionStatus.DISPUTED,
        }:
            raise api_error(AppError.PROPOSAL_NOT_CANCELLABLE, f"missionStatus: {mission.status}")

        paid = proposal.status != ProposalStatus.HOLDING
        if paid:
            proposal.mark_refund_pending(admin_note)
        else:
            proposal.admin_cancel(admin_note)

        offers = (
            db.query(Offer)
            .filter(Offer.proposal_id == proposal.id, Offer.status.in_(CANCELLABLE_OFFER_STATUSES))
            .order_by(Offer.id)
            .populate_existing()
            .with_for_update()
            .all()
        )
        for offer in offers:
            offer.admin_cancel()

        # 미션에는 취소 상태가 없다. 입금액을 돌려줘야 하므로 환불 대상인 실패로 종결한다.
        if mission is not None and not mission.is_terminal():
            mission.mark_failed()
        if paid:
            RefundService.create_pending(
                db,
                proposal,
                RefundReason.ADMIN_CANCELLED,
                reason_detail=admin_note,
                mission=mission,
            )
        else:
            # 입금 확인 전이라 실제 입금 여부를 알 수 없다. 관리자 대조 대기로 남긴다.
            RefundService.create_review(
                db,
                proposal,
                RefundReason.ADMIN_CANCELLED,
                reason_detail=admin_note,
            )
        ChatLifecycle.on_admin_cancelled(db, proposal.id, after_match=mission is not None)
        create_before_offer_notice(db, proposal, NotificationType.PROPOSAL_CANCELLED_BY_ADMIN)

        db.commit()
        return AdminQueryService.get_proposal_detail(db, proposal_id)

    @staticmethod
    def confirm_payment_open_chat_url(db: Session, proposal: Proposal, open_chat_url: str) -> None:
        """입금 확인과 함께 오픈채팅방 URL을 요청에 저장한다."""
        proposal.open_chat_url = open_chat_url

    # ---------------------------------------------------------------- 분쟁

    @staticmethod
    def _get_pending_evidence(db: Session, dispute_id: int) -> DisputeEvidence:
        evidence = db.query(DisputeEvidence).filter(DisputeEvidence.id == dispute_id).first()
        if evidence is None:
            raise api_error(AppError.DISPUTE_EVIDENCE_NOT_FOUND, f"id: {dispute_id}")
        if not evidence.is_pending():
            raise api_error(AppError.DISPUTE_ALREADY_REVIEWED, f"status: {evidence.status}")
        return evidence

    @staticmethod
    def resolve_dispute(
        db: Session,
        dispute_id: int,
        outcome: MissionResolution,
        admin_id: str | None,
        admin_note: str | None,
    ) -> AdminDisputeDetailResponse:
        """분쟁을 판정하고 요청·지원·미션을 함께 종결한다."""
        evidence = AdminCommandService._get_pending_evidence(db, dispute_id)

        proposal = lock_proposal(db, evidence.proposal_id)
        offer = lock_offer(db, evidence.offer_id)
        if proposal is None:
            raise api_error(AppError.PROPOSAL_NOT_FOUND, f"id: {evidence.proposal_id}")
        if offer is None:
            raise api_error(AppError.OFFER_NOT_FOUND, f"id: {evidence.offer_id}")

        mission = lock_mission_of_offer(db, offer.id)
        if mission is None:
            raise api_error(AppError.MISSION_NOT_FOUND, f"offerId: {offer.id}")
        if not mission.can_resolve():
            raise api_error(AppError.MISSION_NOT_RESOLVABLE, f"status: {mission.status}")

        previous_mission_status = mission.status
        if outcome == MissionResolution.COMPLETED:
            offer.resolve_completed()
            proposal.resolve_completed()
            mission.mark_completed()
        else:
            offer.resolve_cancelled()
            proposal.resolve_refund_pending()
            mission.mark_failed()
            RefundService.create_pending(
                db,
                proposal,
                RefundReason.DISPUTE_FAILED,
                reason_detail=evidence.reason,
                mission=mission,
            )
        mission.resolution = outcome.value
        mission.resolved_at = mission.completed_at or mission.failed_at
        mission.resolved_by_admin_id = admin_id

        evidence.mark_resolved(admin_id, admin_note)
        ChatLifecycle.on_dispute_resolved(db, offer.id, completed=outcome == MissionResolution.COMPLETED)

        MissionService.publish_transition_alert(db, mission, proposal, previous_mission_status)
        db.commit()
        return AdminQueryService.get_dispute_detail(db, dispute_id)

    # ------------------------------------------------------- 환불 / 수행비 지급

    @staticmethod
    def _get_mission(db: Session, mission_id: int) -> Mission:
        mission = db.query(Mission).filter(Mission.id == mission_id).first()
        if mission is None:
            raise api_error(AppError.MISSION_NOT_FOUND, f"id: {mission_id}")
        return mission

    @staticmethod
    def _get_refund(db: Session, refund_id: int) -> Refund:
        refund = db.query(Refund).filter(Refund.id == refund_id).first()
        if refund is None:
            raise api_error(AppError.REFUND_NOT_FOUND, f"id: {refund_id}")
        return refund

    @staticmethod
    def complete_refund(
        db: Session, refund_id: int, admin_id: str | None, admin_note: str | None
    ) -> AdminRefundDetailResponse:
        """환불 완료를 기록하고 요청을 REFUNDED로 종결한다."""
        refund = AdminCommandService._get_refund(db, refund_id)
        # 같은 환불을 동시에 완료하지 않게 요청 → 환불 순서로 잠그고 다시 읽는다.
        proposal = lock_proposal(db, refund.proposal_id)
        refund = db.query(Refund).filter(Refund.id == refund_id).populate_existing().with_for_update().one()
        if refund.status != RefundStatus.PENDING:
            raise api_error(AppError.REFUND_NOT_PROCESSABLE, f"status: {refund.status}")

        if proposal is None:
            raise api_error(AppError.PROPOSAL_NOT_FOUND, f"id: {refund.proposal_id}")
        if proposal.status != ProposalStatus.REFUND_PENDING:
            raise api_error(AppError.REFUND_NOT_PROCESSABLE, f"proposalStatus: {proposal.status.value}")

        refund.complete(admin_id, admin_note)
        proposal.mark_refunded()
        ChatLifecycle.on_refund_completed(db, refund)
        create_before_offer_notice(db, proposal, NotificationType.REFUND_COMPLETED)
        db.commit()
        return AdminQueryService.get_refund_detail(db, refund_id)

    @staticmethod
    def confirm_refund_deposit(db: Session, refund_id: int) -> AdminRefundDetailResponse:
        """대조 결과 입금이 확인된 건을 환불 대상으로 확정한다."""
        refund = AdminCommandService._get_refund(db, refund_id)
        if refund.status != RefundStatus.REVIEW:
            raise api_error(AppError.REFUND_NOT_PROCESSABLE, f"status: {refund.status}")

        proposal = db.query(Proposal).filter(Proposal.id == refund.proposal_id).first()
        if proposal is None:
            raise api_error(AppError.PROPOSAL_NOT_FOUND, f"id: {refund.proposal_id}")
        if proposal.status != ProposalStatus.CANCELLED:
            raise api_error(AppError.REFUND_NOT_PROCESSABLE, f"proposalStatus: {proposal.status.value}")

        refund.confirm_deposit()
        # 기존 환불 완료 흐름을 그대로 태우기 위해 요청을 환불 대기로 올린다.
        proposal.confirm_late_deposit()
        db.commit()
        return AdminQueryService.get_refund_detail(db, refund_id)

    @staticmethod
    def void_refund(
        db: Session, refund_id: int, admin_id: str | None, admin_note: str
    ) -> AdminRefundDetailResponse:
        """대조 결과 입금이 없어 환불 없이 종결한다. 요청은 취소 상태로 남는다."""
        refund = AdminCommandService._get_refund(db, refund_id)
        if refund.status != RefundStatus.REVIEW:
            raise api_error(AppError.REFUND_NOT_PROCESSABLE, f"status: {refund.status}")

        refund.void(admin_id, admin_note)
        db.commit()
        return AdminQueryService.get_refund_detail(db, refund_id)

    @staticmethod
    def complete_payout(
        db: Session, payout_id: int, admin_id: str | None, admin_note: str | None
    ) -> AdminPayoutDetailResponse:
        """수행비 지급 완료를 기록한다. 요청·지원 상태는 바꾸지 않는다."""
        mission = AdminCommandService._get_mission(db, payout_id)
        # 같은 지급을 동시에 기록하지 않게 요청 → 임무 순서로 잠그고 다시 읽는다.
        lock_proposal(db, mission.proposal_id)
        mission = lock_mission(db, payout_id)
        if not mission.can_record_settlement():
            raise api_error(AppError.MISSION_NOT_SETTLEABLE, f"status: {mission.status}")

        mission.record_settlement(admin_id, admin_note)
        ChatLifecycle.on_payout_completed(db, mission)
        db.commit()
        return AdminQueryService.get_payout_detail(db, payout_id)

    @staticmethod
    def reject_payout(
        db: Session, payout_id: int, admin_id: str | None, admin_note: str | None
    ) -> AdminPayoutDetailResponse:
        """수행비 지급을 반려한다. 요청·지원 상태는 바꾸지 않는다."""
        mission = AdminCommandService._get_mission(db, payout_id)
        if not mission.can_reject_settlement():
            raise api_error(AppError.MISSION_NOT_SETTLEABLE, f"status: {mission.status}")

        mission.reject_settlement(admin_id, admin_note)
        db.commit()
        return AdminQueryService.get_payout_detail(db, payout_id)


__all__ = ["CANCELLABLE_OFFER_STATUSES", "AdminCommandService"]
