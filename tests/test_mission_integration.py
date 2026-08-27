"""미션 엔티티 생성, 상태 동기화, 관리자 판정과 지급 기록을 검증한다."""

from __future__ import annotations

from app.core.time import utcnow_naive
from app.models.mission import Mission, MissionStatus
from app.models.offer import Offer, OfferStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.dispute_survey import DisputeSurveyQuestion, DisputeSurveyTargetType
from app.models.refund import Refund, RefundReason


def _mission_for(db, offer: Offer) -> Mission:
    return db.query(Mission).filter(Mission.offer_id == offer.id).first()


def _survey_question(db, target_type: DisputeSurveyTargetType) -> DisputeSurveyQuestion:
    question = DisputeSurveyQuestion(
        target_type=target_type,
        question_text="사유",
        display_order=1,
        is_active=True,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


def test_accepting_offer_starts_mission(client, db, factory, sample_user):
    runner = factory.user("01055550001")
    proposal = factory.proposal(sample_user.id, ProposalStatus.OFFERED)
    offer = factory.offer(proposal.id, runner.id, OfferStatus.WAITING)

    response = client.post(f"/v1/offer/{offer.id}/accept", headers=factory.headers_for(sample_user))

    assert response.status_code == 201
    mission = _mission_for(db, offer)
    assert mission is not None
    assert mission.status == MissionStatus.STARTED.value
    assert mission.proposal_id == proposal.id
    assert mission.orderer_id == sample_user.id
    assert mission.runner_id == runner.id
    assert mission.errand_fee == proposal.errand_fee
    assert mission.settlement_paid is False


def test_accept_response_does_not_expose_mission(client, factory, sample_user):
    runner = factory.user("01055550002")
    proposal = factory.proposal(sample_user.id, ProposalStatus.OFFERED)
    offer = factory.offer(proposal.id, runner.id, OfferStatus.WAITING)

    response = client.post(f"/v1/offer/{offer.id}/accept", headers=factory.headers_for(sample_user))

    data = response.json()["data"]
    assert "missionId" not in data
    assert "missionStatus" not in data


def test_both_side_confirmation_completes_mission(client, db, factory, sample_user):
    runner = factory.user("01055550003")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    mission = factory.mission(proposal, offer)

    client.post(f"/v1/offer/{offer.id}/complete-delivery", headers=factory.headers_for(runner))
    client.post(f"/v1/proposal/{proposal.id}/confirm-received", headers=factory.headers_for(sample_user))

    db.refresh(mission)
    db.refresh(offer)
    assert offer.status == OfferStatus.ALL_COMPLETED
    assert mission.status == MissionStatus.COMPLETED.value
    assert mission.completed_at is not None
    assert mission.settlement_paid is False


def test_runner_dispute_moves_mission_to_disputed(client, db, factory, sample_user):
    runner = factory.user("01055550004")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    mission = factory.mission(proposal, offer)
    question = _survey_question(db, DisputeSurveyTargetType.RUNNER)

    response = client.post(
        f"/v1/offer/{offer.id}/dispute",
        headers=factory.headers_for(runner),
        json={"reasonQuestionId": question.id, "detailReason": "행님이 연락을 받지 않습니다."},
    )

    assert response.status_code == 200
    db.refresh(mission)
    assert mission.status == MissionStatus.DISPUTED.value
    assert mission.disputed_at is not None


def test_orderer_dispute_moves_mission_to_disputed(client, db, factory, sample_user):
    runner = factory.user("01055550005")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    mission = factory.mission(proposal, offer)
    question = _survey_question(db, DisputeSurveyTargetType.ORDER)

    response = client.post(
        f"/v1/proposal/{proposal.id}/dispute",
        headers=factory.headers_for(sample_user),
        json={"reasonQuestionId": question.id, "detailReason": "물건을 받지 못했습니다."},
    )

    assert response.status_code == 200
    db.refresh(mission)
    assert mission.status == MissionStatus.DISPUTED.value


def test_admin_resolves_dispute_as_completed(client, db, factory, sample_user, admin_headers):
    runner = factory.user("01055550006")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.DISPUTED, OfferStatus.DISPUTED)
    mission = factory.mission(proposal, offer, MissionStatus.DISPUTED)

    response = client.post(f"/v1/admin/missions/{mission.id}/resolve", json={"resolution": "COMPLETED"}, headers=admin_headers)

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "COMPLETED"
    assert body["resolution"] == "COMPLETED"
    assert body["settlementPaid"] is False
    db.refresh(mission)
    db.refresh(offer)
    db.refresh(proposal)
    assert mission.resolved_at is not None
    assert offer.status == OfferStatus.ALL_COMPLETED
    assert proposal.status == ProposalStatus.ALL_COMPLETED


def test_admin_resolves_dispute_as_failed(client, db, factory, sample_user, admin_headers):
    runner = factory.user("01055550007")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.DISPUTED, OfferStatus.DISPUTED)
    mission = factory.mission(proposal, offer, MissionStatus.DISPUTED)

    response = client.post(f"/v1/admin/missions/{mission.id}/resolve", json={"resolution": "FAILED"}, headers=admin_headers)

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "FAILED"
    assert body["resolution"] == "FAILED"
    db.refresh(mission)
    db.refresh(offer)
    db.refresh(proposal)
    assert mission.failed_at is not None
    assert offer.status == OfferStatus.CANCELLED
    assert proposal.status == ProposalStatus.REFUND_PENDING
    refund = db.query(Refund).filter(Refund.mission_id == mission.id).one()
    assert refund.reason == RefundReason.DISPUTE_FAILED.value


def test_resolve_rejects_mission_that_is_not_disputed(client, factory, sample_user, admin_headers):
    runner = factory.user("01055550008")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    mission = factory.mission(proposal, offer)

    response = client.post(f"/v1/admin/missions/{mission.id}/resolve", json={"resolution": "FAILED"}, headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MISSION_NOT_RESOLVABLE"


def test_resolve_requires_resolution_field(client, factory, sample_user, admin_headers):
    runner = factory.user("01055550009")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.DISPUTED, OfferStatus.DISPUTED)
    mission = factory.mission(proposal, offer, MissionStatus.DISPUTED)

    response = client.post(f"/v1/admin/missions/{mission.id}/resolve", json={}, headers=admin_headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_settlement_marks_mission_paid(client, db, factory, sample_user, admin_headers):
    runner = factory.user("01055550010")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.ALL_COMPLETED, OfferStatus.ALL_COMPLETED)
    mission = factory.mission(proposal, offer, MissionStatus.COMPLETED)

    response = client.post(
        f"/v1/admin/missions/{mission.id}/settlement",
        json={"adminId": sample_user.id, "memo": "이체 참조번호 20260601-001"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "PAID"
    assert body["settlementPaid"] is True
    db.refresh(mission)
    assert mission.settlement_paid_at is not None
    assert mission.settlement_paid_by_admin_id == sample_user.id
    assert mission.payout_memo == "이체 참조번호 20260601-001"


def test_settlement_rejects_mission_that_is_not_completed(client, factory, sample_user, admin_headers):
    runner = factory.user("01055550012")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    mission = factory.mission(proposal, offer)

    response = client.post(f"/v1/admin/missions/{mission.id}/settlement", json={}, headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MISSION_NOT_SETTLEABLE"


def test_duplicate_settlement_is_rejected(client, factory, sample_user, admin_headers):
    runner = factory.user("01055550014")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.ALL_COMPLETED, OfferStatus.ALL_COMPLETED)
    mission = factory.mission(proposal, offer, MissionStatus.COMPLETED)

    first = client.post(f"/v1/admin/missions/{mission.id}/settlement", json={}, headers=admin_headers)
    second = client.post(f"/v1/admin/missions/{mission.id}/settlement", json={}, headers=admin_headers)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "MISSION_NOT_SETTLEABLE"


def test_terminal_mission_is_not_resolvable(client, factory, sample_user, admin_headers):
    runner = factory.user("01055550015")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.ALL_COMPLETED, OfferStatus.ALL_COMPLETED)
    mission = factory.mission(proposal, offer, MissionStatus.PAID)

    response = client.post(f"/v1/admin/missions/{mission.id}/resolve", json={"resolution": "FAILED"}, headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MISSION_NOT_RESOLVABLE"


def test_mission_not_found_returns_404(client, admin_headers):
    response = client.get("/v1/admin/missions/99999", headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MISSION_NOT_FOUND"


def test_mission_detail_exposes_each_side_confirmation_time(client, db, factory, sample_user, admin_headers):
    """관리자가 누가 언제 눌렀는지 미션 한 곳에서 볼 수 있어야 한다."""
    runner = factory.user("01055550020")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    mission = factory.mission(proposal, offer)

    before = client.get(f"/v1/admin/missions/{mission.id}", headers=admin_headers).json()["data"]
    assert before["runnerConfirmedAt"] is None
    assert before["ordererConfirmedAt"] is None

    client.post(f"/v1/offer/{offer.id}/complete-delivery", headers=factory.headers_for(runner))

    after_runner = client.get(f"/v1/admin/missions/{mission.id}", headers=admin_headers).json()["data"]
    assert after_runner["runnerConfirmedAt"] is not None
    assert after_runner["ordererConfirmedAt"] is None
    assert after_runner["status"] == "STARTED"

    client.post(f"/v1/proposal/{proposal.id}/confirm-received", headers=factory.headers_for(sample_user))

    after_both = client.get(f"/v1/admin/missions/{mission.id}", headers=admin_headers).json()["data"]
    assert after_both["runnerConfirmedAt"] is not None
    assert after_both["ordererConfirmedAt"] is not None
    assert after_both["status"] == "COMPLETED"


def test_mission_list_exposes_confirmation_times(client, factory, sample_user, admin_headers):
    runner = factory.user("01055550021")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    factory.mission(proposal, offer)
    client.post(f"/v1/offer/{offer.id}/complete-delivery", headers=factory.headers_for(runner))

    response = client.get("/v1/admin/missions", headers=admin_headers)

    item = response.json()["data"]["content"][0]
    assert item["runnerConfirmedAt"] is not None
    assert item["ordererConfirmedAt"] is None


def test_mission_detail_exposes_participant_names(client, factory, sample_user, admin_headers):
    """관리자 웹이 행님·꼬붕을 UUID가 아닌 이름으로 식별할 수 있어야 한다."""
    runner = factory.user("01055550022", name="꼬붕 하나")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    mission = factory.mission(proposal, offer)

    data = client.get(f"/v1/admin/missions/{mission.id}", headers=admin_headers).json()["data"]

    assert data["ordererName"] == sample_user.name
    assert data["runnerName"] == "꼬붕 하나"


def test_mission_list_exposes_participant_names(client, factory, sample_user, admin_headers):
    runner = factory.user("01055550023", name="꼬붕 둘")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    factory.mission(proposal, offer)

    item = client.get("/v1/admin/missions", headers=admin_headers).json()["data"]["content"][0]

    assert item["ordererName"] == sample_user.name
    assert item["runnerName"] == "꼬붕 둘"


def test_mission_detail_exposes_proposal_open_chat_url(client, db, factory, sample_user, admin_headers):
    """지원에 링크가 없으면 입금 확인 때 요청에 저장한 링크를 반환한다."""
    runner = factory.user("01055550025")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    proposal.open_chat_url = "https://open.kakao.com/o/proposal"
    mission = factory.mission(proposal, offer)
    db.commit()

    data = client.get(f"/v1/admin/missions/{mission.id}", headers=admin_headers).json()["data"]

    assert data["openChatUrl"] == "https://open.kakao.com/o/proposal"


def test_mission_list_returns_proposal_open_chat_url(client, db, factory, sample_user, admin_headers):
    """목록도 상세와 같이 입금 확인 때 요청에 저장한 링크를 내려준다."""
    runner = factory.user("01055550026")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    proposal.open_chat_url = "https://open.kakao.com/o/proposal"
    factory.mission(proposal, offer)
    db.commit()

    item = client.get("/v1/admin/missions", headers=admin_headers).json()["data"]["content"][0]

    assert item["openChatUrl"] == "https://open.kakao.com/o/proposal"


def test_mission_name_uses_display_text_for_withdrawn_participant(client, db, factory, sample_user, admin_headers):
    """탈퇴해 이름이 지워져도 관리자 화면에는 식별 가능한 문구를 내려준다."""
    runner = factory.user("01055550024", name="탈퇴 예정")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    mission = factory.mission(proposal, offer)
    runner.withdraw(utcnow_naive())
    db.commit()

    response = client.get(f"/v1/admin/missions/{mission.id}", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["data"]["runnerName"] == "탈퇴한 사용자"


def test_mission_detail_exposes_payout_flags(client, factory, sample_user, admin_headers):
    runner = factory.user("01055550016")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    mission = factory.mission(proposal, offer)

    response = client.get(f"/v1/admin/missions/{mission.id}", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == mission.id
    assert data["errandFee"] == proposal.errand_fee
    assert data["settlementPaid"] is False


def test_mission_list_filters_by_status(client, factory, sample_user, admin_headers):
    runner_one = factory.user("01055550017")
    runner_two = factory.user("01055550018")
    started_proposal, started_offer = factory.execution(
        sample_user, runner_one, ProposalStatus.MATCHED, OfferStatus.ACCEPTED
    )
    disputed_proposal, disputed_offer = factory.execution(
        sample_user, runner_two, ProposalStatus.DISPUTED, OfferStatus.DISPUTED
    )
    factory.mission(started_proposal, started_offer)
    disputed = factory.mission(disputed_proposal, disputed_offer, MissionStatus.DISPUTED)

    response = client.get("/v1/admin/missions", params={"status": "DISPUTED"}, headers=admin_headers)

    assert response.status_code == 200
    content = response.json()["data"]["content"]
    assert [item["id"] for item in content] == [disputed.id]


def test_offer_resolve_endpoint_is_removed(client, factory, sample_user, admin_headers):
    runner = factory.user("01055550019")
    _, offer = factory.execution(sample_user, runner, ProposalStatus.DISPUTED, OfferStatus.DISPUTED)

    response = client.post(f"/v1/admin/offer/{offer.id}/resolve", headers=admin_headers)

    assert response.status_code == 404
