"""관리자 웹 콘솔 API 통합 테스트."""

from __future__ import annotations

import pytest

from app.models.dispute_evidence import DisputeEvidence, DisputeProcessStatus
from app.models.mission import Mission, MissionStatus
from app.models.offer import OfferStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.proposal_report import ProposalReport, ProposalReportStatus
from app.models.refund import Refund, RefundReason
from app.models.settlement import SettlementAccount


@pytest.fixture
def runner(factory):
    return factory.user(phone="01088887777", name="꼬붕")


def _account(db, user_id: str, holder: str) -> SettlementAccount:
    account = SettlementAccount(
        user_id=user_id,
        bank_name="국민은행",
        account_holder=holder,
        encrypted_account_number="123456789012",
        masked_account_number="********9012",
    )
    db.add(account)
    db.commit()
    return account


# ----------------------------------------------------------------- 요청


def test_list_proposals_filters_by_status_and_counts_offers(client, factory, sample_user, runner, admin_headers):
    holding = factory.proposal(sample_user.id, ProposalStatus.HOLDING)
    posted = factory.proposal(sample_user.id, ProposalStatus.POSTED)
    factory.offer(posted.id, runner.id)

    response = client.get("/v1/admin/proposal", params={"status": "POSTED"}, headers=admin_headers)

    assert response.status_code == 200
    content = response.json()["data"]["content"]
    assert [item["id"] for item in content] == [posted.id]
    assert content[0]["offerCount"] == 1
    assert content[0]["ordererName"] == sample_user.name
    assert holding.id not in [item["id"] for item in content]


def test_list_proposals_keyword_matches_id_and_orderer_name(client, factory, sample_user, admin_headers):
    proposal = factory.proposal(sample_user.id, ProposalStatus.POSTED)

    by_id = client.get("/v1/admin/proposal", params={"keyword": str(proposal.id)}, headers=admin_headers)
    by_name = client.get("/v1/admin/proposal", params={"keyword": "Test"}, headers=admin_headers)

    assert [item["id"] for item in by_id.json()["data"]["content"]] == [proposal.id]
    assert [item["id"] for item in by_name.json()["data"]["content"]] == [proposal.id]


def test_get_proposal_detail_exposes_accepted_offer_and_mission(client, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner)
    mission = factory.mission(proposal, offer)

    response = client.get(f"/v1/admin/proposal/{proposal.id}", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["acceptedOfferId"] == offer.id
    assert data["acceptedRunnerName"] == runner.name
    assert data["missionId"] == mission.id
    assert data["depositorName"] is None


def test_get_proposal_detail_returns_not_found(client, admin_headers):
    response = client.get("/v1/admin/proposal/999999", headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROPOSAL_NOT_FOUND"


def test_cancel_proposal_cascades_offer_and_mission(client, db, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner)
    mission = factory.mission(proposal, offer)

    response = client.post(f"/v1/admin/proposal/{proposal.id}/cancel", json={"adminNote": "행님 요청"}, headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "REFUND_PENDING"
    assert response.json()["data"]["adminNote"] == "행님 요청"
    db.refresh(offer)
    db.refresh(mission)
    assert offer.status == OfferStatus.CANCELLED
    assert mission.status == MissionStatus.FAILED.value
    refund = db.query(Refund).filter(Refund.mission_id == mission.id).one()
    assert refund.reason == RefundReason.ADMIN_CANCELLED.value
    assert refund.reason_detail == "행님 요청"


def test_cancel_proposal_rejects_already_cancelled(client, factory, sample_user, admin_headers):
    proposal = factory.proposal(sample_user.id, ProposalStatus.CANCELLED)

    response = client.post(f"/v1/admin/proposal/{proposal.id}/cancel", json={}, headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROPOSAL_NOT_CANCELLABLE"


def test_cancel_paid_pre_match_proposal_creates_admin_refund(client, db, factory, sample_user, admin_headers):
    proposal = factory.proposal(sample_user.id, ProposalStatus.POSTED)

    response = client.post(
        f"/v1/admin/proposal/{proposal.id}/cancel",
        json={"adminNote": "운영 취소"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "REFUND_PENDING"
    refund = db.query(Refund).filter(Refund.proposal_id == proposal.id).one()
    assert refund.mission_id is None
    assert refund.reason == RefundReason.ADMIN_CANCELLED.value
    assert refund.reason_detail == "운영 취소"


def test_pending_payment_returns_page_of_holding_proposals(client, factory, sample_user, admin_headers):
    holding = factory.proposal(sample_user.id, ProposalStatus.HOLDING)
    factory.proposal(sample_user.id, ProposalStatus.POSTED)

    response = client.get("/v1/admin/proposal/pending-payment", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert [item["id"] for item in data["content"]] == [holding.id]
    assert data["pageSize"] == 20


# ----------------------------------------------------------------- 지원


def test_list_offers_reports_amount_accepted_and_dispute_flags(client, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner)
    factory.mission(proposal, offer)
    factory.dispute_evidence(proposal, offer, sample_user.id)

    response = client.get("/v1/admin/offer", params={"proposalId": proposal.id}, headers=admin_headers)

    assert response.status_code == 200
    item = response.json()["data"]["content"][0]
    assert item["amount"] == proposal.errand_fee
    assert item["accepted"] is True
    assert item["hasDispute"] is True
    assert item["runnerName"] == runner.name


def test_list_offers_filters_by_dispute_absence(client, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner)

    response = client.get("/v1/admin/offer", params={"hasDispute": "true"}, headers=admin_headers)

    assert response.json()["data"]["content"] == []

    response = client.get("/v1/admin/offer", params={"hasDispute": "false"}, headers=admin_headers)
    assert [item["id"] for item in response.json()["data"]["content"]] == [offer.id]


def test_list_offers_keeps_cancelled_mission_offer_in_accepted_filter(
    client, factory, sample_user, runner, admin_headers
):
    proposal, offer = factory.execution(
        sample_user,
        runner,
        ProposalStatus.REFUND_PENDING,
        OfferStatus.CANCELLED,
    )
    factory.mission(proposal, offer, MissionStatus.FAILED)

    response = client.get("/v1/admin/offer", params={"accepted": "true"}, headers=admin_headers)

    assert [item["id"] for item in response.json()["data"]["content"]] == [offer.id]
    assert response.json()["data"]["content"][0]["accepted"] is True


# ----------------------------------------------------------------- 분쟁


def test_list_and_get_dispute_resolves_requester_and_target_roles(client, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.DISPUTED, OfferStatus.DISPUTED)
    mission = factory.mission(proposal, offer, MissionStatus.DISPUTED)
    evidence = factory.dispute_evidence(proposal, offer, sample_user.id)

    listed = client.get("/v1/admin/dispute", params={"status": "PENDING"}, headers=admin_headers)
    assert [item["id"] for item in listed.json()["data"]["content"]] == [evidence.id]
    assert listed.json()["data"]["content"][0]["missionId"] == mission.id
    assert listed.json()["data"]["content"][0]["requesterRole"] == "ORDERER"

    detail = client.get(f"/v1/admin/dispute/{evidence.id}", headers=admin_headers)
    data = detail.json()["data"]
    assert data["requesterRole"] == "ORDERER"
    assert data["targetId"] == runner.id
    assert data["targetRole"] == "RUNNER"
    assert data["proposalStatus"] == "DISPUTED"


def test_resolve_dispute_completes_mission_and_closes_proposal(client, db, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.DISPUTED, OfferStatus.DISPUTED)
    mission = factory.mission(proposal, offer, MissionStatus.DISPUTED)
    evidence = factory.dispute_evidence(proposal, offer, sample_user.id)

    response = client.post(
        f"/v1/admin/dispute/{evidence.id}/resolve",
        json={"outcome": "COMPLETED", "adminNote": "꼬붕 과실 없음"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "RESOLVED"
    db.refresh(mission)
    db.refresh(proposal)
    db.refresh(offer)
    assert mission.status == MissionStatus.COMPLETED.value
    assert mission.resolution == "COMPLETED"
    assert proposal.status == ProposalStatus.ALL_COMPLETED
    assert offer.status == OfferStatus.ALL_COMPLETED


def test_resolve_dispute_with_failed_outcome_marks_mission_failed(client, db, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.DISPUTED, OfferStatus.DISPUTED)
    mission = factory.mission(proposal, offer, MissionStatus.DISPUTED)
    evidence = factory.dispute_evidence(proposal, offer, sample_user.id)

    response = client.post(f"/v1/admin/dispute/{evidence.id}/resolve", json={"outcome": "FAILED"}, headers=admin_headers)

    assert response.status_code == 200
    db.refresh(mission)
    db.refresh(proposal)
    db.refresh(offer)
    assert mission.status == MissionStatus.FAILED.value
    assert proposal.status == ProposalStatus.REFUND_PENDING
    assert offer.status == OfferStatus.CANCELLED
    refund = db.query(Refund).filter(Refund.mission_id == mission.id).one()
    assert refund.reason == RefundReason.DISPUTE_FAILED.value
    assert refund.reason_detail == evidence.reason


def test_reject_dispute_leaves_other_statuses_untouched(client, db, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.DISPUTED, OfferStatus.DISPUTED)
    mission = factory.mission(proposal, offer, MissionStatus.DISPUTED)
    evidence = factory.dispute_evidence(proposal, offer, sample_user.id)

    response = client.post(f"/v1/admin/dispute/{evidence.id}/reject", json={"adminNote": "증빙 부족"}, headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "REJECTED"
    db.refresh(mission)
    db.refresh(proposal)
    assert mission.status == MissionStatus.DISPUTED.value
    assert proposal.status == ProposalStatus.DISPUTED


def test_resolve_dispute_rejects_already_reviewed(client, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.DISPUTED, OfferStatus.DISPUTED)
    factory.mission(proposal, offer, MissionStatus.DISPUTED)
    evidence = factory.dispute_evidence(
        proposal, offer, sample_user.id, status=DisputeProcessStatus.RESOLVED.value
    )

    response = client.post(f"/v1/admin/dispute/{evidence.id}/resolve", json={"outcome": "COMPLETED"}, headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DISPUTE_ALREADY_REVIEWED"


# ----------------------------------------------------------- 환불 / 수행비 지급


def test_list_refunds_returns_pending_refunds_with_proposal_status(client, db, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.REFUND_PENDING, OfferStatus.CANCELLED)
    mission = factory.mission(proposal, offer, MissionStatus.FAILED)
    refund = factory.refund(proposal, mission)

    response = client.get("/v1/admin/refund", params={"status": "PENDING"}, headers=admin_headers)

    assert response.status_code == 200
    item = response.json()["data"]["content"][0]
    assert item["id"] == refund.id
    assert item["proposalStatus"] == "REFUND_PENDING"
    assert item["amount"] == proposal.errand_fee
    assert item["status"] == "PENDING"
    assert item["reason"] == "DISPUTE_FAILED"


def test_list_refunds_filters_by_proposal_id(client, db, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.REFUND_PENDING, OfferStatus.CANCELLED)
    mission = factory.mission(proposal, offer, MissionStatus.FAILED)
    refund = factory.refund(proposal, mission)
    other_proposal, other_offer = factory.execution(
        sample_user, runner, ProposalStatus.REFUND_PENDING, OfferStatus.CANCELLED
    )
    other_mission = factory.mission(other_proposal, other_offer, MissionStatus.FAILED)
    factory.refund(other_proposal, other_mission)

    response = client.get("/v1/admin/refund", params={"proposalId": proposal.id}, headers=admin_headers)

    assert response.status_code == 200
    content = response.json()["data"]["content"]
    assert [item["id"] for item in content] == [refund.id]
    assert content[0]["proposalId"] == proposal.id


def test_get_refund_detail_exposes_unmasked_account(client, db, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.REFUND_PENDING, OfferStatus.CANCELLED)
    mission = factory.mission(proposal, offer, MissionStatus.FAILED)
    refund = factory.refund(proposal, mission)
    _account(db, sample_user.id, "행님")

    response = client.get(f"/v1/admin/refund/{refund.id}", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["refundAccountNumber"] == "123456789012"
    assert data["refundAccountHolder"] == "행님"
    assert data["reason"] == "DISPUTE_FAILED"
    assert data["reasonDetail"] == "약속한 물건과 다른 물건을 전달했습니다."


def test_complete_refund_records_and_cancels_proposal(client, db, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.REFUND_PENDING, OfferStatus.CANCELLED)
    mission = factory.mission(proposal, offer, MissionStatus.FAILED)
    refund = factory.refund(proposal, mission)

    response = client.post(f"/v1/admin/refund/{refund.id}/complete", json={"adminNote": "이체 완료"}, headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "COMPLETED"
    db.refresh(mission)
    db.refresh(proposal)
    assert mission.status == MissionStatus.FAILED.value
    assert proposal.status == ProposalStatus.REFUNDED


def test_list_payouts_returns_completed_missions(client, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.ALL_COMPLETED, OfferStatus.ALL_COMPLETED)
    mission = factory.mission(proposal, offer, MissionStatus.COMPLETED)

    response = client.get("/v1/admin/payout", params={"status": "PENDING"}, headers=admin_headers)

    assert response.status_code == 200
    item = response.json()["data"]["content"][0]
    assert item["id"] == mission.id
    assert item["runnerName"] == runner.name
    assert item["errandFee"] == proposal.errand_fee
    assert item["status"] == "COMPLETED"
    assert item["settlementStatus"] == "PENDING"


def test_complete_payout_records_settlement(client, db, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.ALL_COMPLETED, OfferStatus.ALL_COMPLETED)
    mission = factory.mission(proposal, offer, MissionStatus.COMPLETED)
    _account(db, runner.id, "꼬붕")

    response = client.post(f"/v1/admin/payout/{mission.id}/complete", json={"adminNote": "이체 완료"}, headers=admin_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "COMPLETED"
    assert data["payoutAccountNumber"] == "123456789012"
    db.refresh(mission)
    db.refresh(proposal)
    assert mission.status == MissionStatus.PAID.value
    assert proposal.status == ProposalStatus.ALL_COMPLETED


def test_reject_payout_keeps_mission_status(client, db, factory, sample_user, runner, admin_headers):
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.ALL_COMPLETED, OfferStatus.ALL_COMPLETED)
    mission = factory.mission(proposal, offer, MissionStatus.COMPLETED)

    response = client.post(f"/v1/admin/payout/{mission.id}/reject", json={"adminNote": "계좌 미등록"}, headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "REJECTED"
    db.refresh(mission)
    assert mission.status == MissionStatus.COMPLETED.value


def test_payout_not_found(client, admin_headers):
    response = client.get("/v1/admin/payout/999999", headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MISSION_NOT_FOUND"


# ----------------------------------------------------------------- 대시보드


def test_summary_counts_pending_work_per_domain(client, db, factory, sample_user, runner, admin_headers):
    factory.proposal(sample_user.id, ProposalStatus.HOLDING)

    disputed_proposal, disputed_offer = factory.execution(
        sample_user, runner, ProposalStatus.DISPUTED, OfferStatus.DISPUTED
    )
    factory.mission(disputed_proposal, disputed_offer, MissionStatus.DISPUTED)
    factory.dispute_evidence(disputed_proposal, disputed_offer, sample_user.id)

    failed_proposal, failed_offer = factory.execution(
        sample_user, runner, ProposalStatus.REFUND_PENDING, OfferStatus.CANCELLED
    )
    failed_mission = factory.mission(failed_proposal, failed_offer, MissionStatus.FAILED)
    factory.refund(failed_proposal, failed_mission)

    completed_proposal, completed_offer = factory.execution(
        sample_user, runner, ProposalStatus.ALL_COMPLETED, OfferStatus.ALL_COMPLETED
    )
    factory.mission(completed_proposal, completed_offer, MissionStatus.COMPLETED)

    db.add(
        ProposalReport(
            proposal_id=completed_proposal.id,
            reporter_id=runner.id,
            reason_question_id=1,
            status=ProposalReportStatus.PENDING,
        )
    )
    db.commit()

    response = client.get("/v1/admin/summary", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["data"] == {
        "unpaidCount": 1,
        "disputeCount": 1,
        "refundCount": 1,
        "settlementCount": 1,
        "reportCount": 1,
    }
