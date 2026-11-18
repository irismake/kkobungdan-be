"""Mission business logic. 관리자 웹 전용이며 앱 API에는 노출하지 않는다."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import AppError, api_error
from app.events.base import EventBus
from app.events.mission_events import MissionCompletedEvent, MissionDisputedEvent
from app.models.dispute_evidence import DisputeEvidence
from app.models.mission import Mission, MissionResolution, MissionStatus
from app.models.offer import Offer, OfferStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.refund import RefundReason
from app.schemas.common import PageResponse
from app.schemas.mission import MissionResponse
from app.services.admin.admin_user_display import WITHDRAWN_USER_NAME, admin_user_names
from app.services.chat.chat_lifecycle import ChatLifecycle
from app.services.locking import lock_mission, lock_mission_of_offer, lock_offer, lock_proposal
from app.services.refund.refund_service import RefundService


#: 미션이 존재해야 하는 지원 상태. 이 밖의 상태에서는 미션을 만들지 않는다.
MISSION_OFFER_STATUSES = (
    OfferStatus.ACCEPTED,
    OfferStatus.RUNNER_COMPLETED,
    OfferStatus.ALL_COMPLETED,
    OfferStatus.DISPUTED,
)


class MissionService:
    """Service layer for Mission commands and admin queries."""

    @staticmethod
    def _get_mission(db: Session, mission_id: int) -> Mission:
        mission = db.query(Mission).filter(Mission.id == mission_id).first()
        if mission is None:
            raise api_error(AppError.MISSION_NOT_FOUND)
        return mission

    @staticmethod
    def _lock_mission(db: Session, mission_id: int) -> tuple[Mission, Proposal | None]:
        """요청 → 임무 순서로 잠그고 최신 값으로 읽는다. 판정·지급처럼 임무 상태를 바꾸기 전에 쓴다."""
        proposal_id = db.query(Mission.proposal_id).filter(Mission.id == mission_id).scalar()
        if proposal_id is None:
            raise api_error(AppError.MISSION_NOT_FOUND)
        proposal = lock_proposal(db, proposal_id)
        offer_id = db.query(Mission.offer_id).filter(Mission.id == mission_id).scalar()
        lock_offer(db, offer_id)
        mission = lock_mission(db, mission_id)
        if mission is None:
            raise api_error(AppError.MISSION_NOT_FOUND)
        return mission, proposal

    @staticmethod
    def _find_by_offer(db: Session, offer_id: int) -> Mission | None:
        # 요청·지원을 잠근 뒤 부르므로 임무도 잠가 최신 값으로 읽는다 (app/services/locking.py).
        return lock_mission_of_offer(db, offer_id)

    @staticmethod
    def create_for_accepted_offer(db: Session, offer: Offer, proposal: Proposal) -> Mission:
        """지원 수락 시 미션을 생성한다. 이미 있으면 그대로 돌려준다."""
        existing = MissionService._find_by_offer(db, offer.id)
        if existing is not None:
            return existing

        mission = Mission.start(
            proposal_id=proposal.id,
            offer_id=offer.id,
            orderer_id=proposal.orderer_id,
            runner_id=offer.runner_id,
            errand_fee=proposal.errand_fee,
        )
        db.add(mission)
        db.flush()
        return mission

    @staticmethod
    def sync_from_offer_and_proposal(db: Session, offer: Offer, proposal: Proposal) -> Mission | None:
        """요청·지원 상태 변화를 미션 상태에 반영한다.

        지급·환불이 끝난 종료 상태는 건드리지 않는다. 분쟁 판정으로 이미 완료 또는 실패가
        확정된 미션도 요청·지원 상태에 따라 되돌리지 않는다.
        """
        mission = MissionService._find_by_offer(db, offer.id)
        if mission is None:
            return None
        if mission.is_terminal():
            return mission

        previous_status = mission.status
        if offer.status == OfferStatus.DISPUTED or proposal.status == ProposalStatus.DISPUTED:
            mission.mark_disputed()
        elif offer.status == OfferStatus.ALL_COMPLETED and proposal.status == ProposalStatus.ALL_COMPLETED:
            mission.mark_completed()
        MissionService.publish_transition_alert(db, mission, proposal, previous_status)
        return mission

    @staticmethod
    def publish_transition_alert(
        db: Session,
        mission: Mission,
        proposal: Proposal,
        previous_status: MissionStatus | str,
    ) -> None:
        """미션 상태가 실제로 바뀐 경우에만 관리자 알림 이벤트를 발행한다.

        `mark_disputed`/`mark_completed`는 허용되지 않는 상태에서 조용히 아무것도 하지 않으므로
        호출했다는 사실만으로는 전이 여부를 알 수 없다. 전후 상태를 비교하지 않으면 이미
        분쟁중인 미션에 같은 알림이 반복해서 나간다.

        관리자가 처리해야 진행되는 두 상태만 알린다. `FAILED`와 `PAID`는 관리자 본인의
        조작 결과라 다시 알릴 이유가 없다.
        """
        if mission.status == previous_status:
            return

        payload = {
            "mission_id": mission.id,
            "proposal_id": mission.proposal_id,
            "offer_id": mission.offer_id,
            "proposal_title": proposal.title,
            "errand_fee": mission.errand_fee,
            "orderer_id": mission.orderer_id,
            "runner_id": mission.runner_id,
        }
        if mission.status == MissionStatus.DISPUTED:
            EventBus.publish(MissionDisputedEvent(**payload), db)
        elif mission.status == MissionStatus.COMPLETED:
            EventBus.publish(MissionCompletedEvent(**payload), db)

    @staticmethod
    def resolve_dispute(
        db: Session,
        mission_id: int,
        resolution: MissionResolution,
        admin_id: str | None = None,
    ) -> MissionResponse:
        """관리자가 분쟁 미션을 완료 또는 실패로 판정한다.

        판정과 함께 요청·지원을 완료 또는 환불/취소 상태로 종결한다.
        """
        mission, _ = MissionService._lock_mission(db, mission_id)
        if not mission.can_resolve():
            raise api_error(AppError.MISSION_NOT_RESOLVABLE, f"status: {mission.status}")

        offer = db.query(Offer).filter(Offer.id == mission.offer_id).first()
        proposal = db.query(Proposal).filter(Proposal.id == mission.proposal_id).first()
        if offer is None:
            raise api_error(AppError.OFFER_NOT_FOUND)
        if proposal is None:
            raise api_error(AppError.PROPOSAL_NOT_FOUND)
        evidence = (
            db.query(DisputeEvidence)
            .filter(DisputeEvidence.mission_id == mission.id)
            .order_by(DisputeEvidence.created_at.desc(), DisputeEvidence.id.desc())
            .first()
        )

        previous_status = mission.status
        if resolution == MissionResolution.COMPLETED:
            if offer.can_resolve():
                offer.resolve_completed()
            if proposal.can_resolve():
                proposal.resolve_completed()
            mission.mark_completed()
        else:
            if offer.can_resolve():
                offer.resolve_cancelled()
            if proposal.can_resolve():
                proposal.resolve_refund_pending()
            mission.mark_failed()
            RefundService.create_pending(
                db,
                proposal,
                RefundReason.DISPUTE_FAILED,
                reason_detail=evidence.reason if evidence is not None else None,
                mission=mission,
            )
        mission.resolution = resolution.value
        mission.resolved_at = mission.completed_at or mission.failed_at
        mission.resolved_by_admin_id = admin_id
        if evidence is not None and evidence.is_pending():
            evidence.mark_resolved(admin_id, None)
        ChatLifecycle.on_dispute_resolved(db, offer.id, completed=resolution == MissionResolution.COMPLETED)

        MissionService.publish_transition_alert(db, mission, proposal, previous_status)
        db.commit()
        db.refresh(mission)
        return MissionService._detail_response(db, mission)

    @staticmethod
    def record_settlement(
        db: Session,
        mission_id: int,
        admin_id: str | None = None,
        memo: str | None = None,
    ) -> MissionResponse:
        """꼬붕에게 수행비를 입금한 사실을 기록한다. 금액은 요청의 수행비 전액이다."""
        mission, _ = MissionService._lock_mission(db, mission_id)
        if not mission.can_record_settlement():
            raise api_error(AppError.MISSION_NOT_SETTLEABLE, f"status: {mission.status}")

        mission.record_settlement(admin_id, memo)
        ChatLifecycle.on_payout_completed(db, mission)
        db.commit()
        db.refresh(mission)
        return MissionService._detail_response(db, mission)

    @staticmethod
    def get_detail(db: Session, mission_id: int) -> MissionResponse:
        mission = MissionService._get_mission(db, mission_id)
        return MissionService._detail_response(db, mission)

    @staticmethod
    def search(
        db: Session,
        statuses: list[MissionStatus] | None,
        page: int,
        size: int,
    ) -> PageResponse[MissionResponse]:
        query = db.query(Mission)
        if statuses:
            query = query.filter(Mission.status.in_(statuses))

        total = query.count()
        missions = (
            query.order_by(Mission.started_at.desc(), Mission.id.desc())
            .offset(page * size)
            .limit(size)
            .all()
        )
        return PageResponse.of(
            content=MissionService.to_responses(db, missions),
            page_number=page,
            page_size=size,
            total_elements=total,
        )

    @staticmethod
    def to_responses(db: Session, missions: list[Mission]) -> list[MissionResponse]:
        """미션 목록을 이름·지원 상세와 함께 한 번에 응답으로 변환한다."""
        offer_details = MissionService._offer_details(db, [mission.offer_id for mission in missions])
        names = MissionService._names(
            db,
            [user_id for mission in missions for user_id in (mission.orderer_id, mission.runner_id)],
        )
        return [MissionService._to_response(mission, offer_details, names) for mission in missions]

    @staticmethod
    def _names(db: Session, user_ids: list[str]) -> dict[str, str]:
        """행님·꼬붕 이름을 한 번에 읽어 온다. 목록마다 N+1 조회를 하지 않기 위해서다."""
        return admin_user_names(db, user_ids)

    @staticmethod
    def _detail_response(db: Session, mission: Mission) -> MissionResponse:
        """미션 한 건을 이름·확인 시각까지 채워 응답으로 만든다."""
        return MissionService._to_response(
            mission,
            MissionService._offer_details(db, [mission.offer_id]),
            MissionService._names(db, [mission.orderer_id, mission.runner_id]),
        )

    @staticmethod
    def _offer_details(db: Session, offer_ids: list[int]) -> dict[int, tuple]:
        """완료 확인 시각과 오픈채팅 URL을 지원·요청에서 한 번에 읽어 온다.

        미션에 복제해 저장하지 않고 조회 시점에 합친다. 오픈채팅방 URL은 관리자가
        입금을 확인할 때 요청에 저장한다.
        """
        if not offer_ids:
            return {}
        rows = (
            db.query(
                Offer.id,
                Offer.runner_confirmed_at,
                Offer.orderer_confirmed_at,
                Proposal.open_chat_url,
            )
            .join(Proposal, Proposal.id == Offer.proposal_id)
            .filter(Offer.id.in_(offer_ids))
            .all()
        )
        return {row[0]: (row[1], row[2], row[3]) for row in rows}

    @staticmethod
    def _to_response(
        mission: Mission,
        offer_details: dict[int, tuple],
        names: dict[str, str],
    ) -> MissionResponse:
        runner_confirmed_at, orderer_confirmed_at, open_chat_url = offer_details.get(
            mission.offer_id,
            (None, None, None),
        )
        values = {column.name: getattr(mission, column.name) for column in Mission.__table__.columns}
        values.update(
            orderer_name=names.get(mission.orderer_id) or WITHDRAWN_USER_NAME,
            runner_name=names.get(mission.runner_id) or WITHDRAWN_USER_NAME,
            open_chat_url=open_chat_url,
            runner_confirmed_at=runner_confirmed_at,
            orderer_confirmed_at=orderer_confirmed_at,
            settlement_paid=mission.settlement_paid,
            settlement_status=mission.settlement_status,
        )
        return MissionResponse.model_validate(values)


__all__ = ["MISSION_OFFER_STATUSES", "MissionService"]
