"""Admin console read models. 관리자 웹 목록·상세·집계 조회를 담당한다."""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, api_error
from app.models.dispute_evidence import DisputeEvidence, DisputeProcessStatus
from app.models.mission import Mission, MissionStatus, PayoutStatus
from app.models.offer import Offer, OfferStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.proposal_report import ProposalReport, ProposalReportStatus
from app.models.refund import Refund, RefundReason, RefundStatus
from app.models.settlement import SettlementAccount
from app.models.user import User
from app.schemas.admin import (
    ORDERER_ROLE,
    RUNNER_ROLE,
    AdminDisputeDetailResponse,
    AdminDisputeSummaryResponse,
    AdminOfferSummaryResponse,
    AdminPayoutDetailResponse,
    AdminProposalDetailResponse,
    AdminProposalSummaryResponse,
    AdminRefundDetailResponse,
    AdminRefundSummaryResponse,
    AdminSummaryResponse,
)
from app.schemas.common import PageResponse
from app.schemas.mission import MissionResponse
from app.services.admin.admin_user_display import WITHDRAWN_USER_NAME, admin_user_names
from app.services.mission.mission_service import MissionService


#: 요청이 수락된 지원으로 실행 중임을 뜻하는 지원 상태.
ACCEPTED_OFFER_STATUSES = (
    OfferStatus.ACCEPTED,
    OfferStatus.RUNNER_COMPLETED,
    OfferStatus.ALL_COMPLETED,
    OfferStatus.DISPUTED,
)


def _names(db: Session, user_ids: list[str]) -> dict[str, str]:
    """사용자 이름을 한 번에 읽어 온다. 목록마다 N+1 조회를 하지 않기 위해서다."""
    return admin_user_names(db, user_ids)


def _name(names: dict[str, str], user_id: str) -> str:
    """관리자 응답의 필수 이름을 항상 표시 가능한 값으로 돌려준다."""
    return names.get(user_id) or WITHDRAWN_USER_NAME


def _levels(db: Session, user_ids: list[str]) -> dict[str, int]:
    unique_ids = {user_id for user_id in user_ids if user_id}
    if not unique_ids:
        return {}
    rows = db.query(User.id, User.level).filter(User.id.in_(unique_ids)).all()
    return {row[0]: row[1] or 0 for row in rows}


def _as_int(keyword: str) -> int | None:
    try:
        return int(keyword)
    except (TypeError, ValueError):
        return None


class AdminQueryService:
    """관리자 조회 전용 서비스. 상태를 바꾸지 않는다."""

    # ---------------------------------------------------------------- 요청

    @staticmethod
    def list_proposals(
        db: Session,
        statuses: list[ProposalStatus] | None,
        keyword: str | None,
        page: int,
        size: int,
    ) -> PageResponse[AdminProposalSummaryResponse]:
        query = db.query(Proposal)
        if statuses:
            query = query.filter(Proposal.status.in_(statuses))
        if keyword:
            conditions = [Proposal.orderer_id.in_(AdminQueryService._user_ids_by_name(db, keyword))]
            proposal_id = _as_int(keyword)
            if proposal_id is not None:
                conditions.append(Proposal.id == proposal_id)
            query = query.filter(or_(*conditions))

        total = query.count()
        proposals = (
            query.order_by(Proposal.created_at.desc(), Proposal.id.desc())
            .offset(page * size)
            .limit(size)
            .all()
        )

        names = _names(db, [proposal.orderer_id for proposal in proposals])
        offer_counts = AdminQueryService._offer_counts(db, [proposal.id for proposal in proposals])
        content = [
            AdminProposalSummaryResponse(
                id=proposal.id,
                orderer_id=proposal.orderer_id,
                orderer_name=_name(names, proposal.orderer_id),
                errand_fee=proposal.errand_fee,
                status=proposal.status,
                offer_count=offer_counts.get(proposal.id, 0),
                created_at=proposal.created_at,
            )
            for proposal in proposals
        ]
        return PageResponse.of(content=content, page_number=page, page_size=size, total_elements=total)

    @staticmethod
    def get_proposal_detail(db: Session, proposal_id: int) -> AdminProposalDetailResponse:
        proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
        if proposal is None:
            raise api_error(AppError.PROPOSAL_NOT_FOUND, f"id: {proposal_id}")

        mission = db.query(Mission).filter(Mission.proposal_id == proposal.id).first()
        if mission is not None:
            accepted_offer = db.query(Offer).filter(Offer.id == mission.offer_id).first()
        else:
            accepted_offer = (
                db.query(Offer)
                .filter(Offer.proposal_id == proposal.id, Offer.status.in_(ACCEPTED_OFFER_STATUSES))
                .order_by(Offer.accepted_at.desc(), Offer.id.desc())
                .first()
            )

        user_ids = [proposal.orderer_id]
        if accepted_offer is not None:
            user_ids.append(accepted_offer.runner_id)
        names = _names(db, user_ids)
        levels = _levels(db, user_ids)

        return AdminProposalDetailResponse(
            id=proposal.id,
            title=proposal.title,
            content=proposal.content,
            deadline=proposal.deadline,
            errand_fee=proposal.errand_fee,
            orderer_id=proposal.orderer_id,
            orderer_name=_name(names, proposal.orderer_id),
            orderer_level=levels.get(proposal.orderer_id, 0),
            status=proposal.status,
            created_at=proposal.created_at,
            # 수락 이후에는 지원에 붙은 URL이 정본이고, 그 전에는 입금 확인 때 받은 값을 쓴다.
            open_chat_url=(accepted_offer.open_chat_url if accepted_offer else None) or proposal.open_chat_url,
            accepted_offer_id=accepted_offer.id if accepted_offer else None,
            accepted_runner_name=_name(names, accepted_offer.runner_id) if accepted_offer else None,
            mission_id=mission.id if mission else None,
            admin_note=proposal.admin_note,
            depositor_name=None,
            deposit_bank_name=settings.admin_deposit_bank_name,
            deposit_account_number=settings.admin_deposit_account_number,
            deposit_account_holder=settings.admin_deposit_account_holder,
            matched_at=proposal.matched_at,
            runner_confirmed_at=proposal.runner_confirmed_at,
            orderer_confirmed_at=proposal.orderer_confirmed_at,
            disputed_at=proposal.disputed_at,
            resolved_at=proposal.resolved_at,
        )

    @staticmethod
    def _offer_counts(db: Session, proposal_ids: list[int]) -> dict[int, int]:
        if not proposal_ids:
            return {}
        rows = (
            db.query(Offer.proposal_id, func.count(Offer.id))
            .filter(Offer.proposal_id.in_(proposal_ids))
            .group_by(Offer.proposal_id)
            .all()
        )
        return {row[0]: row[1] for row in rows}

    @staticmethod
    def _user_ids_by_name(db: Session, keyword: str) -> list[str]:
        rows = db.query(User.id).filter(User.name.ilike(f"%{keyword}%")).all()
        return [row[0] for row in rows]

    # ---------------------------------------------------------------- 지원

    @staticmethod
    def list_offers(
        db: Session,
        proposal_id: int | None,
        statuses: list[OfferStatus] | None,
        accepted: bool | None,
        has_dispute: bool | None,
        keyword: str | None,
        page: int,
        size: int,
    ) -> PageResponse[AdminOfferSummaryResponse]:
        query = db.query(Offer)
        if proposal_id is not None:
            query = query.filter(Offer.proposal_id == proposal_id)
        if statuses:
            query = query.filter(Offer.status.in_(statuses))
        if accepted is not None:
            mission_offer_ids = db.query(Mission.offer_id)
            if accepted:
                query = query.filter(
                    or_(
                        Offer.status.in_(ACCEPTED_OFFER_STATUSES),
                        Offer.id.in_(mission_offer_ids),
                    )
                )
            else:
                query = query.filter(
                    Offer.status.notin_(ACCEPTED_OFFER_STATUSES),
                    Offer.id.notin_(mission_offer_ids),
                )
        if has_dispute is not None:
            disputed_offer_ids = db.query(DisputeEvidence.offer_id).distinct()
            if has_dispute:
                query = query.filter(Offer.id.in_(disputed_offer_ids))
            else:
                query = query.filter(Offer.id.notin_(disputed_offer_ids))
        if keyword:
            conditions = [Offer.runner_id.in_(AdminQueryService._user_ids_by_name(db, keyword))]
            numeric = _as_int(keyword)
            if numeric is not None:
                conditions.append(Offer.id == numeric)
                conditions.append(Offer.proposal_id == numeric)
            query = query.filter(or_(*conditions))

        total = query.count()
        offers = (
            query.order_by(Offer.created_at.desc(), Offer.id.desc()).offset(page * size).limit(size).all()
        )

        names = _names(db, [offer.runner_id for offer in offers])
        levels = _levels(db, [offer.runner_id for offer in offers])
        fees = AdminQueryService._errand_fees(db, [offer.proposal_id for offer in offers])
        disputed_offer_ids = AdminQueryService._disputed_offer_ids(db, [offer.id for offer in offers])
        offer_ids = [offer.id for offer in offers]
        accepted_offer_ids = {
            row[0]
            for row in db.query(Mission.offer_id).filter(Mission.offer_id.in_(offer_ids)).all()
        }

        content = [
            AdminOfferSummaryResponse(
                id=offer.id,
                proposal_id=offer.proposal_id,
                runner_id=offer.runner_id,
                runner_name=_name(names, offer.runner_id),
                runner_level=levels.get(offer.runner_id, 0),
                status=offer.status,
                accepted=offer.id in accepted_offer_ids or offer.status in ACCEPTED_OFFER_STATUSES,
                has_dispute=offer.id in disputed_offer_ids,
                amount=fees.get(offer.proposal_id, 0),
                open_chat_url=offer.open_chat_url,
                created_at=offer.created_at,
            )
            for offer in offers
        ]
        return PageResponse.of(content=content, page_number=page, page_size=size, total_elements=total)

    @staticmethod
    def _errand_fees(db: Session, proposal_ids: list[int]) -> dict[int, int]:
        unique_ids = set(proposal_ids)
        if not unique_ids:
            return {}
        rows = db.query(Proposal.id, Proposal.errand_fee).filter(Proposal.id.in_(unique_ids)).all()
        return {row[0]: row[1] for row in rows}

    @staticmethod
    def _disputed_offer_ids(db: Session, offer_ids: list[int]) -> set[int]:
        if not offer_ids:
            return set()
        rows = (
            db.query(DisputeEvidence.offer_id)
            .filter(DisputeEvidence.offer_id.in_(set(offer_ids)))
            .distinct()
            .all()
        )
        return {row[0] for row in rows}

    # ---------------------------------------------------------------- 분쟁

    @staticmethod
    def list_disputes(
        db: Session,
        statuses: list[DisputeProcessStatus] | None,
        proposal_id: int | None,
        keyword: str | None,
        page: int,
        size: int,
    ) -> PageResponse[AdminDisputeSummaryResponse]:
        query = db.query(DisputeEvidence)
        if statuses:
            query = query.filter(DisputeEvidence.status.in_([status.value for status in statuses]))
        if proposal_id is not None:
            query = query.filter(DisputeEvidence.proposal_id == proposal_id)
        if keyword:
            conditions = [DisputeEvidence.actor_id.in_(AdminQueryService._user_ids_by_name(db, keyword))]
            numeric = _as_int(keyword)
            if numeric is not None:
                conditions.append(DisputeEvidence.id == numeric)
                conditions.append(DisputeEvidence.proposal_id == numeric)
                conditions.append(DisputeEvidence.offer_id == numeric)
            query = query.filter(or_(*conditions))

        total = query.count()
        evidences = (
            query.order_by(DisputeEvidence.created_at.desc(), DisputeEvidence.id.desc())
            .offset(page * size)
            .limit(size)
            .all()
        )
        names = _names(db, [evidence.actor_id for evidence in evidences])
        orderer_ids = AdminQueryService._orderer_ids(db, [evidence.proposal_id for evidence in evidences])

        content = [
            AdminDisputeSummaryResponse(
                id=evidence.id,
                proposal_id=evidence.proposal_id,
                offer_id=evidence.offer_id,
                mission_id=evidence.mission_id,
                requester_id=evidence.actor_id,
                requester_name=_name(names, evidence.actor_id),
                requester_role=(
                    ORDERER_ROLE if orderer_ids.get(evidence.proposal_id) == evidence.actor_id else RUNNER_ROLE
                ),
                status=DisputeProcessStatus(evidence.status),
                created_at=evidence.created_at,
            )
            for evidence in evidences
        ]
        return PageResponse.of(content=content, page_number=page, page_size=size, total_elements=total)

    @staticmethod
    def get_dispute_detail(db: Session, dispute_id: int) -> AdminDisputeDetailResponse:
        evidence = db.query(DisputeEvidence).filter(DisputeEvidence.id == dispute_id).first()
        if evidence is None:
            raise api_error(AppError.DISPUTE_EVIDENCE_NOT_FOUND, f"id: {dispute_id}")

        proposal = db.query(Proposal).filter(Proposal.id == evidence.proposal_id).first()
        offer = db.query(Offer).filter(Offer.id == evidence.offer_id).first()
        if proposal is None:
            raise api_error(AppError.PROPOSAL_NOT_FOUND, f"id: {evidence.proposal_id}")
        if offer is None:
            raise api_error(AppError.OFFER_NOT_FOUND, f"id: {evidence.offer_id}")

        requester_is_orderer = evidence.actor_id == proposal.orderer_id
        target_id = offer.runner_id if requester_is_orderer else proposal.orderer_id
        names = _names(db, [evidence.actor_id, target_id])

        return AdminDisputeDetailResponse(
            id=evidence.id,
            proposal_id=evidence.proposal_id,
            offer_id=evidence.offer_id,
            mission_id=evidence.mission_id,
            requester_id=evidence.actor_id,
            requester_name=_name(names, evidence.actor_id),
            requester_role=ORDERER_ROLE if requester_is_orderer else RUNNER_ROLE,
            status=DisputeProcessStatus(evidence.status),
            created_at=evidence.created_at,
            target_id=target_id,
            target_name=_name(names, target_id),
            target_role=RUNNER_ROLE if requester_is_orderer else ORDERER_ROLE,
            survey_question_id=evidence.survey_question_id,
            reason=evidence.reason,
            proposal_status=proposal.status,
            offer_status=offer.status,
            admin_note=evidence.admin_note,
            resolved_at=evidence.resolved_at,
        )

    @staticmethod
    def _orderer_ids(db: Session, proposal_ids: list[int]) -> dict[int, str]:
        unique_ids = set(proposal_ids)
        if not unique_ids:
            return {}
        rows = db.query(Proposal.id, Proposal.orderer_id).filter(Proposal.id.in_(unique_ids)).all()
        return {row[0]: row[1] for row in rows}

    # ------------------------------------------------------- 환불 / 수행비 지급

    @staticmethod
    def _payout_status_filter(query, statuses: list[PayoutStatus] | None):
        """수행비 지급 상태는 미션 필드에서 파생하므로 조건으로 풀어 쓴다."""
        if not statuses:
            return query

        paid_at = Mission.settlement_paid_at
        rejected_at = Mission.settlement_rejected_at
        pending_status = MissionStatus.COMPLETED.value
        done_status = MissionStatus.PAID.value

        conditions = []
        for status in statuses:
            if status == PayoutStatus.PENDING:
                conditions.append(
                    (Mission.status == pending_status) & paid_at.is_(None) & rejected_at.is_(None)
                )
            elif status == PayoutStatus.COMPLETED:
                conditions.append(Mission.status == done_status)
            else:
                conditions.append(rejected_at.isnot(None) & paid_at.is_(None))
        return query.filter(or_(*conditions))

    @staticmethod
    def list_refunds(
        db: Session,
        statuses: list[RefundStatus] | None,
        requested_from: date | None,
        keyword: str | None,
        proposal_id: int | None,
        page: int,
        size: int,
    ) -> PageResponse[AdminRefundSummaryResponse]:
        query = db.query(Refund)
        if statuses:
            query = query.filter(Refund.status.in_([status.value for status in statuses]))
        if requested_from is not None:
            query = query.filter(Refund.requested_at >= datetime.combine(requested_from, time.min))
        if proposal_id is not None:
            query = query.filter(Refund.proposal_id == proposal_id)
        if keyword:
            conditions = [Refund.orderer_id.in_(AdminQueryService._user_ids_by_name(db, keyword))]
            numeric = _as_int(keyword)
            if numeric is not None:
                conditions.append(Refund.id == numeric)
                conditions.append(Refund.proposal_id == numeric)
            query = query.filter(or_(*conditions))

        total = query.count()
        refunds = (
            query.order_by(Refund.requested_at.desc(), Refund.id.desc()).offset(page * size).limit(size).all()
        )
        names = _names(db, [refund.orderer_id for refund in refunds])
        proposal_statuses = AdminQueryService._proposal_statuses(db, [refund.proposal_id for refund in refunds])

        content = [
            AdminRefundSummaryResponse(
                id=refund.id,
                proposal_id=refund.proposal_id,
                proposal_status=proposal_statuses[refund.proposal_id],
                orderer_id=refund.orderer_id,
                orderer_name=_name(names, refund.orderer_id),
                amount=refund.amount,
                status=RefundStatus(refund.status),
                reason=RefundReason(refund.reason),
                requested_at=refund.requested_at,
                processed_at=refund.processed_at,
            )
            for refund in refunds
        ]
        return PageResponse.of(content=content, page_number=page, page_size=size, total_elements=total)

    @staticmethod
    def get_refund_detail(db: Session, refund_id: int) -> AdminRefundDetailResponse:
        refund = db.query(Refund).filter(Refund.id == refund_id).first()
        if refund is None:
            raise api_error(AppError.REFUND_NOT_FOUND, f"id: {refund_id}")
        proposal_statuses = AdminQueryService._proposal_statuses(db, [refund.proposal_id])
        names = _names(db, [refund.orderer_id])
        account = AdminQueryService._settlement_account(db, refund.orderer_id)

        return AdminRefundDetailResponse(
            id=refund.id,
            proposal_id=refund.proposal_id,
            proposal_status=proposal_statuses[refund.proposal_id],
            orderer_id=refund.orderer_id,
            orderer_name=_name(names, refund.orderer_id),
            amount=refund.amount,
            status=RefundStatus(refund.status),
            requested_at=refund.requested_at,
            processed_at=refund.processed_at,
            reason=RefundReason(refund.reason),
            reason_detail=refund.reason_detail,
            refund_bank_name=account.bank_name if account else None,
            refund_account_number=account.encrypted_account_number if account else None,
            refund_account_holder=account.account_holder if account else None,
            admin_note=refund.admin_note,
        )

    @staticmethod
    def list_payouts(
        db: Session,
        statuses: list[PayoutStatus] | None,
        proposal_id: int | None,
        keyword: str | None,
        page: int,
        size: int,
    ) -> PageResponse[MissionResponse]:
        query = db.query(Mission).filter(
            Mission.status.in_([MissionStatus.COMPLETED.value, MissionStatus.PAID.value])
        )
        query = AdminQueryService._payout_status_filter(query, statuses)
        if proposal_id is not None:
            query = query.filter(Mission.proposal_id == proposal_id)
        if keyword:
            conditions = [Mission.runner_id.in_(AdminQueryService._user_ids_by_name(db, keyword))]
            numeric = _as_int(keyword)
            if numeric is not None:
                conditions.append(Mission.id == numeric)
                conditions.append(Mission.proposal_id == numeric)
                conditions.append(Mission.offer_id == numeric)
            query = query.filter(or_(*conditions))

        total = query.count()
        missions = (
            query.order_by(Mission.completed_at.desc(), Mission.id.desc()).offset(page * size).limit(size).all()
        )
        content = MissionService.to_responses(db, missions)
        return PageResponse.of(content=content, page_number=page, page_size=size, total_elements=total)

    @staticmethod
    def get_payout_detail(db: Session, payout_id: int) -> AdminPayoutDetailResponse:
        mission = AdminQueryService._get_mission(db, payout_id)
        names = _names(db, [mission.runner_id])
        account = AdminQueryService._settlement_account(db, mission.runner_id)

        return AdminPayoutDetailResponse(
            id=mission.id,
            proposal_id=mission.proposal_id,
            offer_id=mission.offer_id,
            runner_id=mission.runner_id,
            runner_name=_name(names, mission.runner_id),
            amount=mission.errand_fee,
            status=mission.settlement_status,
            settled_at=mission.settlement_paid_at or mission.settlement_rejected_at,
            payout_bank_name=account.bank_name if account else None,
            payout_account_number=account.encrypted_account_number if account else None,
            payout_account_holder=account.account_holder if account else None,
            admin_note=mission.payout_memo,
        )

    @staticmethod
    def _get_mission(db: Session, mission_id: int) -> Mission:
        mission = db.query(Mission).filter(Mission.id == mission_id).first()
        if mission is None:
            raise api_error(AppError.MISSION_NOT_FOUND, f"id: {mission_id}")
        return mission

    @staticmethod
    def _settlement_account(db: Session, user_id: str) -> SettlementAccount | None:
        return db.query(SettlementAccount).filter(SettlementAccount.user_id == user_id).first()

    @staticmethod
    def _proposal_statuses(db: Session, proposal_ids: list[int]) -> dict[int, ProposalStatus]:
        unique_ids = set(proposal_ids)
        if not unique_ids:
            return {}
        rows = db.query(Proposal.id, Proposal.status).filter(Proposal.id.in_(unique_ids)).all()
        return {row[0]: row[1] for row in rows}

    # ------------------------------------------------------------- 대시보드

    @staticmethod
    def summary(db: Session) -> AdminSummaryResponse:
        unpaid = db.query(func.count(Proposal.id)).filter(Proposal.status == ProposalStatus.HOLDING).scalar()
        disputes = (
            db.query(func.count(DisputeEvidence.id))
            .filter(DisputeEvidence.status == DisputeProcessStatus.PENDING.value)
            .scalar()
        )
        refunds = db.query(func.count(Refund.id)).filter(Refund.status == RefundStatus.PENDING.value).scalar()
        settlements = (
            db.query(func.count(Mission.id))
            .filter(
                Mission.status == MissionStatus.COMPLETED.value,
                Mission.settlement_paid_at.is_(None),
                Mission.settlement_rejected_at.is_(None),
            )
            .scalar()
        )
        reports = (
            db.query(func.count(ProposalReport.id))
            .filter(ProposalReport.status == ProposalReportStatus.PENDING)
            .scalar()
        )
        return AdminSummaryResponse(
            unpaid_count=unpaid or 0,
            dispute_count=disputes or 0,
            refund_count=refunds or 0,
            settlement_count=settlements or 0,
            report_count=reports or 0,
        )


__all__ = ["ACCEPTED_OFFER_STATUSES", "AdminQueryService"]
