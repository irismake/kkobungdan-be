"""Shared test data factories."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.dispute_evidence import DisputeEvidence
from app.models.dispute_survey import DisputeSurveyQuestion, DisputeSurveyTargetType
from app.models.mission import Mission, MissionStatus
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.models.offer import Offer, OfferStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.refund import Refund, RefundReason, RefundStatus
from app.models.settlement import SettlementAccount
from app.models.user import User


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TestDataFactory:
    def __init__(self, db: Session):
        self.db = db

    def headers_for(self, user: User) -> dict:
        return {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}

    def user(self, phone: str = "01099990000", name: str = "Test User") -> User:
        user = User(name=name, phone=phone, alarm_enabled=False)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def settlement_account(self, user: User) -> SettlementAccount:
        account = SettlementAccount(
            user_id=user.id,
            bank_name="국민은행",
            account_holder=user.name or "탈퇴한 사용자",
            encrypted_account_number="123456789012",
            masked_account_number="********9012",
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def proposal(
        self,
        orderer_id: str,
        status: ProposalStatus = ProposalStatus.POSTED,
        title: str = "요청",
    ) -> Proposal:
        deadline = datetime.now(timezone.utc) + timedelta(days=1)
        proposal = Proposal(
            orderer_id=orderer_id,
            title=title,
            content="요청 내용",
            deadline=deadline,
            errand_fee=5000,
            status=status,
            meeting_at=deadline,
            item_price=0,
            deposit=0,
        )
        # Set timestamps based on status
        if status in {ProposalStatus.ORDER_COMPLETED, ProposalStatus.ALL_COMPLETED}:
            proposal.orderer_confirmed_at = utcnow_naive()
        if status == ProposalStatus.MATCHED:
            proposal.matched_at = utcnow_naive()
        self.db.add(proposal)
        self.db.commit()
        self.db.refresh(proposal)
        return proposal

    def offer(
        self,
        proposal_id: int,
        runner_id: str,
        status: OfferStatus = OfferStatus.WAITING,
    ) -> Offer:
        offer = Offer(proposal_id=proposal_id, runner_id=runner_id, status=status)
        self.db.add(offer)
        self.db.commit()
        self.db.refresh(offer)
        return offer

    def execution(
        self,
        orderer: User,
        runner: User,
        proposal_status: ProposalStatus = ProposalStatus.MATCHED,
        offer_status: OfferStatus = OfferStatus.ACCEPTED,
    ) -> tuple[Proposal, Offer]:
        proposal = self.proposal(orderer.id, proposal_status)
        offer = self.offer(proposal.id, runner.id, offer_status)
        return proposal, offer

    def mission(
        self,
        proposal: Proposal,
        offer: Offer,
        status: MissionStatus = MissionStatus.STARTED,
        **overrides,
    ) -> Mission:
        mission = Mission.start(
            proposal_id=proposal.id,
            offer_id=offer.id,
            orderer_id=proposal.orderer_id,
            runner_id=offer.runner_id,
            errand_fee=proposal.errand_fee,
        )
        mission.status = status.value
        if status == MissionStatus.DISPUTED:
            mission.disputed_at = utcnow_naive()
        if status in {MissionStatus.COMPLETED, MissionStatus.PAID}:
            mission.completed_at = utcnow_naive()
        if status == MissionStatus.FAILED:
            mission.failed_at = utcnow_naive()
        for key, value in overrides.items():
            setattr(mission, key, value)
        self.db.add(mission)
        self.db.commit()
        self.db.refresh(mission)
        return mission

    def dispute_evidence(self, proposal: Proposal, offer: Offer, actor_id: str, **overrides) -> DisputeEvidence:
        mission = self.db.query(Mission).filter(Mission.offer_id == offer.id).one()
        question = DisputeSurveyQuestion(
            target_type=DisputeSurveyTargetType.ORDER,
            question_text="물건이 파손되었어요",
            display_order=1,
            is_active=True,
        )
        self.db.add(question)
        self.db.commit()
        self.db.refresh(question)
        evidence = DisputeEvidence(
            proposal_id=proposal.id,
            offer_id=offer.id,
            mission_id=mission.id,
            actor_id=actor_id,
            reason="약속한 물건과 다른 물건을 전달했습니다.",
            survey_question_id=question.id,
        )
        for key, value in overrides.items():
            setattr(evidence, key, value)
        self.db.add(evidence)
        self.db.commit()
        self.db.refresh(evidence)
        return evidence

    def refund(
        self,
        proposal: Proposal,
        mission: Mission | None = None,
        reason: RefundReason = RefundReason.DISPUTE_FAILED,
        status: RefundStatus = RefundStatus.PENDING,
        **overrides,
    ) -> Refund:
        refund = Refund(
            proposal_id=proposal.id,
            mission_id=mission.id if mission is not None else None,
            orderer_id=proposal.orderer_id,
            amount=proposal.errand_fee,
            reason=reason.value,
            reason_detail="약속한 물건과 다른 물건을 전달했습니다." if reason == RefundReason.DISPUTE_FAILED else None,
            status=status.value,
        )
        for key, value in overrides.items():
            setattr(refund, key, value)
        self.db.add(refund)
        self.db.commit()
        self.db.refresh(refund)
        return refund

    def notification(self, user_id: str, **overrides) -> Notification:
        values = {
            "user_id": user_id,
            "notification_type": NotificationType.CUSTOM,
            "title": "테스트 알림",
            "body": "테스트 알림 본문입니다.",
            "data": '{"proposalId":1}',
            "related_entity_type": "proposal",
            "related_entity_id": 1,
            "status": NotificationStatus.SENT,
            "fcm_message_id": "projects/orderrun/messages/1",
            "sent_at": utcnow_naive(),
        }
        values.update(overrides)
        notification = Notification(**values)
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification
