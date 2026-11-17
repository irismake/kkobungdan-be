"""Offer business logic."""

from __future__ import annotations

from sqlalchemy import case
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, api_error
from app.events.base import EventBus
from app.events.execution_events import DisputeRaisedByRunnerEvent, MeetingConfirmedByRunnerEvent
from app.events.offer_events import OfferAcceptedEvent, OfferCreatedEvent
from app.models.dispute_survey import DisputeSurveyTargetType
from app.models.chat import ChatRole
from app.models.dispute_evidence import DisputeEvidence
from app.models.offer import Offer, OfferStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.settlement import SettlementAccount
from app.models.user import User
from app.schemas.common import PageResponse
from app.schemas.offer import OfferAcceptResponse, OfferCreate, OfferDetailResponse, OfferResponse, OfferSummaryResponse
from app.services.chat.chat_lifecycle import ChatLifecycle
from app.services.dispute.dispute_survey_service import DisputeSurveyService
from app.services.mission.mission_service import MissionService


OPEN_PROPOSAL_STATUSES = (ProposalStatus.POSTED, ProposalStatus.OFFERED)
ACTIVE_OFFER_STATUSES = (
    OfferStatus.ACCEPTED,
    OfferStatus.RUNNER_COMPLETED,
    OfferStatus.ALL_COMPLETED,
    OfferStatus.DISPUTED,
)
OPEN_CHAT_OFFER_STATUSES = (
    OfferStatus.ACCEPTED,
    OfferStatus.RUNNER_COMPLETED,
    OfferStatus.ALL_COMPLETED,
    OfferStatus.DISPUTED,
)

# 내 활동 - 수행 기록 화면의 배지 노출 순서. 같은 배지 안에서는 최신순으로 정렬한다.
# 배지: 대기중 -> 진행중 -> 분쟁중 -> 완료 -> 취소
OFFER_BADGE_ORDER = (
    (OfferStatus.WAITING,),
    (OfferStatus.ACCEPTED, OfferStatus.RUNNER_COMPLETED),
    (OfferStatus.DISPUTED,),
    (OfferStatus.ALL_COMPLETED,),
    (OfferStatus.REJECTED, OfferStatus.CANCELLED),
)


def _offer_badge_rank():
    """배지 순서를 SQL 정렬식으로 변환한다. 매핑에 없는 상태는 맨 뒤로 보낸다."""
    return case(
        *[(Offer.status.in_(statuses), rank) for rank, statuses in enumerate(OFFER_BADGE_ORDER)],
        else_=len(OFFER_BADGE_ORDER),
    )


class OfferService:
    """Service layer for Offer commands and queries."""

    @staticmethod
    def _get_proposal(db: Session, proposal_id: int) -> Proposal:
        proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
        if proposal is None:
            raise api_error(AppError.PROPOSAL_NOT_FOUND)
        return proposal

    @staticmethod
    def _ensure_proposal_exists(db: Session, proposal_id: int) -> None:
        OfferService._get_proposal(db, proposal_id)

    @staticmethod
    def _get_offer(db: Session, offer_id: int) -> Offer:
        offer = db.query(Offer).filter(Offer.id == offer_id).first()
        if offer is None:
            raise api_error(AppError.OFFER_NOT_FOUND)
        return offer

    @staticmethod
    def _user_profile(db: Session, user_id: str) -> tuple[str, int]:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            return "", 0
        return ("탈퇴한 사용자" if user.deleted else user.name or ""), user.level

    @staticmethod
    def _response_fields(db: Session, offer: Offer) -> dict:
        proposal = OfferService._get_proposal(db, offer.proposal_id)
        orderer_name, orderer_level = OfferService._user_profile(db, proposal.orderer_id)
        runner_name, runner_level = OfferService._user_profile(db, offer.runner_id)
        return {
            "id": offer.id,
            "proposal_id": offer.proposal_id,
            "orderer_id": proposal.orderer_id,
            "orderer_name": orderer_name,
            "orderer_level": orderer_level,
            "runner_id": offer.runner_id,
            "runner_name": runner_name,
            "runner_level": runner_level,
            "status": offer.status,
            "accepted_at": offer.accepted_at,
            "runner_confirmed_at": offer.runner_confirmed_at,
            "orderer_confirmed_at": offer.orderer_confirmed_at,
            "disputed_at": offer.disputed_at,
            "resolved_at": offer.resolved_at,
            "created_at": offer.created_at,
        }

    @staticmethod
    def _to_response(db: Session, offer: Offer) -> OfferResponse:
        return OfferResponse(**OfferService._response_fields(db, offer))

    @staticmethod
    def _to_summary_response(db: Session, offer: Offer) -> OfferSummaryResponse:
        return OfferSummaryResponse(**OfferService._response_fields(db, offer))

    @staticmethod
    def _to_detail_response(db: Session, offer: Offer, viewer_id: str) -> OfferDetailResponse:
        fields = OfferService._response_fields(db, offer)
        open_chat_url = None
        if (
            offer.status in OPEN_CHAT_OFFER_STATUSES
            and viewer_id in {fields["orderer_id"], offer.runner_id}
        ):
            # 오픈채팅방 URL은 관리자가 입금을 확인할 때 요청에 저장한다.
            open_chat_url = OfferService._get_proposal(db, offer.proposal_id).open_chat_url
        return OfferDetailResponse(**fields, open_chat_url=open_chat_url)

    @staticmethod
    def _sync_all_completed(db: Session, offer: Offer, proposal: Proposal) -> None:
        if offer.status == OfferStatus.RUNNER_COMPLETED and proposal.status == ProposalStatus.ORDER_COMPLETED:
            offer.mark_all_completed()
            proposal.mark_all_completed()
            db.query(User).filter(User.id == offer.runner_id).update(
                {User.level: User.level + 1},
                synchronize_session=False,
            )

    @staticmethod
    def create(db: Session, request: OfferCreate, runner_id: str) -> OfferResponse:
        proposal = OfferService._get_proposal(db, request.proposal_id)

        if proposal.orderer_id == runner_id:
            raise api_error(AppError.SELF_OFFER_NOT_ALLOWED)

        if proposal.status not in OPEN_PROPOSAL_STATUSES:
            raise api_error(AppError.PROPOSAL_NOT_OPEN)

        account_exists = (
            db.query(SettlementAccount.id)
            .filter(SettlementAccount.user_id == runner_id)
            .first()
            is not None
        )
        if not account_exists:
            raise api_error(AppError.SETTLEMENT_ACCOUNT_REQUIRED)

        duplicate = (
            db.query(Offer)
            .filter(Offer.proposal_id == request.proposal_id, Offer.runner_id == runner_id)
            .first()
        )
        if duplicate is not None:
            raise api_error(AppError.DUPLICATE_OFFER)

        offer = Offer(proposal_id=request.proposal_id, runner_id=runner_id, status=OfferStatus.WAITING)
        try:
            db.add(offer)
            if proposal.status == ProposalStatus.POSTED:
                proposal.mark_as_offered()
            db.flush()
            # 채팅방·지원 등록 안내·첫 인사를 같은 트랜잭션에 저장한다 (CHAT-REQ-006, CHAT-REQ-023).
            ChatLifecycle.on_offer_created(db, offer, proposal, request.greeting)
            EventBus.publish(OfferCreatedEvent(
                offer_id=offer.id,
                proposal_id=proposal.id,
                runner_id=runner_id,
                orderer_id=proposal.orderer_id,
                proposal_title=proposal.title,
            ), db)
            db.commit()
            db.refresh(offer)
        except IntegrityError as exc:
            db.rollback()
            if "uk_proposal_runner" in str(exc) or "uq_proposal_runner" in str(exc):
                raise api_error(AppError.DUPLICATE_OFFER) from exc
            raise

        return OfferService._to_response(db, offer)

    @staticmethod
    def find_offers_by_proposal(
        db: Session,
        proposal_id: int,
        offer_statuses: list[OfferStatus] | None,
    ) -> list[OfferSummaryResponse]:
        OfferService._ensure_proposal_exists(db, proposal_id)
        query = db.query(Offer).filter(Offer.proposal_id == proposal_id)
        if offer_statuses:
            query = query.filter(Offer.status.in_(offer_statuses))

        offers = query.order_by(Offer.created_at.desc(), Offer.id.desc()).all()
        return [OfferService._to_summary_response(db, offer) for offer in offers]

    @staticmethod
    def get_offer_detail(db: Session, offer_id: int, viewer_id: str) -> OfferDetailResponse:
        offer = OfferService._get_offer(db, offer_id)
        return OfferService._to_detail_response(db, offer, viewer_id)

    @staticmethod
    def search_runner_offers(
        db: Session,
        runner_id: str,
        offer_statuses: list[OfferStatus] | None,
        page: int,
        size: int,
    ) -> PageResponse[OfferResponse]:
        query = db.query(Offer).filter(Offer.runner_id == runner_id)
        if offer_statuses:
            query = query.filter(Offer.status.in_(offer_statuses))

        total = query.count()
        offers = (
            query.order_by(_offer_badge_rank().asc(), Offer.created_at.desc(), Offer.id.desc())
            .offset(page * size)
            .limit(size)
            .all()
        )
        return PageResponse.of(
            content=[OfferService._to_response(db, offer) for offer in offers],
            page_number=page,
            page_size=size,
            total_elements=total,
        )

    @staticmethod
    def cancel(db: Session, offer_id: int, runner_id: str) -> None:
        offer = OfferService._get_offer(db, offer_id)
        if offer.runner_id != runner_id:
            raise api_error(AppError.FORBIDDEN)
        if offer.status != OfferStatus.WAITING:
            raise api_error(AppError.OFFER_NOT_CANCELLABLE)

        offer.cancel()
        ChatLifecycle.on_offer_cancelled(db, offer)
        db.commit()

    @staticmethod
    def accept(db: Session, offer_id: int, orderer_id: str) -> OfferAcceptResponse:
        offer = OfferService._get_offer(db, offer_id)
        proposal = OfferService._get_proposal(db, offer.proposal_id)

        if proposal.orderer_id != orderer_id:
            raise api_error(AppError.FORBIDDEN)

        if offer.status != OfferStatus.WAITING:
            raise api_error(AppError.OFFER_NOT_ACCEPTABLE)

        existing_active_offer = (
            db.query(Offer)
            .filter(
                Offer.proposal_id == proposal.id,
                Offer.id != offer.id,
                Offer.status.in_(ACTIVE_OFFER_STATUSES),
            )
            .first()
        )
        if existing_active_offer is not None:
            raise api_error(AppError.PROPOSAL_NOT_MATCHABLE)

        if proposal.status != ProposalStatus.OFFERED:
            raise api_error(AppError.PROPOSAL_NOT_MATCHABLE)

        rejected_runner_ids = tuple(
            row[0] for row in db.query(Offer.runner_id).filter(
                Offer.proposal_id == proposal.id,
                Offer.id != offer.id,
                Offer.status == OfferStatus.WAITING,
            ).all()
        )

        offer.accept()
        proposal.status = ProposalStatus.MATCHED
        proposal.matched_at = offer.accepted_at
        rejected_count = (
            db.query(Offer)
            .filter(
                Offer.proposal_id == proposal.id,
                Offer.id != offer.id,
                Offer.status == OfferStatus.WAITING,
            )
            .update({Offer.status: OfferStatus.REJECTED}, synchronize_session=False)
        )
        MissionService.create_for_accepted_offer(db, offer, proposal)
        db.flush()
        ChatLifecycle.on_offer_accepted(db, offer)
        EventBus.publish(OfferAcceptedEvent(
            offer_id=offer.id,
            proposal_id=proposal.id,
            accepted_runner_id=offer.runner_id,
            rejected_runner_ids=rejected_runner_ids,
            orderer_id=proposal.orderer_id,
            proposal_title=proposal.title,
        ), db)
        db.commit()
        db.refresh(offer)
        db.refresh(proposal)
        orderer_name, orderer_level = OfferService._user_profile(db, proposal.orderer_id)
        runner_name, runner_level = OfferService._user_profile(db, offer.runner_id)

        return OfferAcceptResponse(
            proposal_id=proposal.id,
            offer_id=offer.id,
            proposal_status=proposal.status,
            accepted_offer_status=offer.status,
            rejected_offer_count=rejected_count,
            orderer_id=proposal.orderer_id,
            orderer_name=orderer_name,
            orderer_level=orderer_level,
            runner_id=offer.runner_id,
            runner_name=runner_name,
            runner_level=runner_level,
            accepted_at=offer.accepted_at,
        )

    @staticmethod
    def complete_delivery(
        db: Session,
        offer_id: int,
        runner_id: str,
    ) -> OfferResponse:
        offer = OfferService._get_offer(db, offer_id)
        if offer.runner_id != runner_id:
            raise api_error(AppError.FORBIDDEN)

        proposal = OfferService._get_proposal(db, offer.proposal_id)
        if not offer.can_confirm_runner_completion() or proposal.status not in {
            ProposalStatus.MATCHED,
            ProposalStatus.ORDER_COMPLETED,
        }:
            raise api_error(AppError.OFFER_NOT_UPDATABLE, f"status: {offer.status.value}")

        offer.confirm_runner_completion()
        if proposal.status in {ProposalStatus.MATCHED, ProposalStatus.ORDER_COMPLETED}:
            proposal.confirm_runner_completion()
        if proposal.status == ProposalStatus.ORDER_COMPLETED:
            offer.confirm_orderer_completion()
        OfferService._sync_all_completed(db, offer, proposal)
        MissionService.sync_from_offer_and_proposal(db, offer, proposal)
        all_completed = offer.status == OfferStatus.ALL_COMPLETED and proposal.status == ProposalStatus.ALL_COMPLETED
        ChatLifecycle.on_runner_completed(db, offer, all_confirmed=all_completed)
        db.flush()
        EventBus.publish(MeetingConfirmedByRunnerEvent(
            offer_id=offer.id,
            proposal_id=proposal.id,
            runner_id=offer.runner_id,
            orderer_id=proposal.orderer_id,
            proposal_title=proposal.title,
            all_completed=all_completed,
        ), db)
        db.commit()
        db.refresh(offer)
        return OfferService._to_response(db, offer)

    @staticmethod
    def raise_dispute(
        db: Session,
        offer_id: int,
        runner_id: str,
        reason_question_id: int,
        detail_reason: str | None = None,
    ) -> OfferResponse:
        offer = OfferService._get_offer(db, offer_id)
        if offer.runner_id != runner_id:
            raise api_error(AppError.FORBIDDEN)

        proposal = OfferService._get_proposal(db, offer.proposal_id)
        if not offer.can_raise_dispute() or not proposal.can_raise_dispute():
            raise api_error(AppError.OFFER_NOT_UPDATABLE, f"status: {offer.status.value}")

        DisputeSurveyService.resolve_reason(db, reason_question_id, detail_reason, DisputeSurveyTargetType.RUNNER)
        offer.raise_dispute()
        proposal.raise_dispute()
        mission = MissionService.sync_from_offer_and_proposal(db, offer, proposal)
        if mission is None:
            raise api_error(AppError.MISSION_NOT_FOUND, f"offerId: {offer.id}")
        db.add(DisputeEvidence(
            proposal_id=proposal.id,
            offer_id=offer.id,
            mission_id=mission.id,
            actor_id=runner_id,
            survey_question_id=reason_question_id,
            reason=detail_reason,
        ))
        db.flush()
        ChatLifecycle.on_dispute_raised(db, offer, raised_by=ChatRole.RUNNER)
        EventBus.publish(DisputeRaisedByRunnerEvent(
            offer_id=offer.id,
            proposal_id=proposal.id,
            runner_id=offer.runner_id,
            orderer_id=proposal.orderer_id,
            proposal_title=proposal.title,
        ), db)
        db.commit()
        db.refresh(offer)
        return OfferService._to_response(db, offer)
