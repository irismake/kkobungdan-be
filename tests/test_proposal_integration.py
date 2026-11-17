from __future__ import annotations

import pytest

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect

from app.models.dispute_survey import DisputeSurveyQuestion, DisputeSurveyTargetType
from app.models.dispute_evidence import DisputeEvidence
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.models.offer import Offer, OfferStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.refund import Refund, RefundReason, RefundStatus
from app.models.settlement import SettlementAccount


def future_deadline(days: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def proposal_payload(**overrides):
    payload = {
        "title": "강남역 커피 배달",
        "content": "스타벅스 아메리카노 아이스 2잔 부탁드립니다.",
        "deadline": future_deadline(),
        "errandFee": 5000,
    }
    payload.update(overrides)
    return payload


def dispute_question(
    target_type: DisputeSurveyTargetType,
    question_text: str = "분쟁 사유를 선택해주세요.",
    display_order: int = 1,
    is_active: bool = True,
    requires_detail: bool = False,
) -> DisputeSurveyQuestion:
    return DisputeSurveyQuestion(
        target_type=target_type,
        question_text=question_text,
        display_order=display_order,
        is_active=is_active,
        requires_detail=requires_detail,
    )


def notification_for(db, user_id: str, notification_type: NotificationType, related_entity_id: int) -> Notification:
    return (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.notification_type == notification_type,
            Notification.related_entity_id == related_entity_id,
        )
        .one()
    )


def notification_count(db, user_id: str, notification_type: NotificationType, related_entity_id: int) -> int:
    return (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.notification_type == notification_type,
            Notification.related_entity_id == related_entity_id,
        )
        .count()
    )


@pytest.mark.scenario("PROPOSAL-TS-001")
def test_list_public_requires_auth_and_supports_multi_status_filter(client, db, factory, auth_headers, sample_user):
    holding = factory.proposal(sample_user.id, ProposalStatus.HOLDING, "holding")
    posted = factory.proposal(sample_user.id, ProposalStatus.POSTED, "posted")
    offered = factory.proposal(sample_user.id, ProposalStatus.OFFERED, "offered")
    matched = factory.proposal(sample_user.id, ProposalStatus.MATCHED, "matched")
    cancelled = factory.proposal(sample_user.id, ProposalStatus.CANCELLED, "cancelled")

    unauthenticated = client.get("/v1/proposal")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "INVALID_TOKEN"

    response = client.get("/v1/proposal", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body["data"]["content"]}
    assert ids == {posted.id, offered.id}
    assert body["data"]["pageNumber"] == 0
    assert body["data"]["pageSize"] == 20
    assert body["data"]["totalElements"] == 2

    filtered = client.get("/v1/proposal?status=HOLDING&status=POSTED", headers=auth_headers)
    assert filtered.status_code == 200
    filtered_ids = {item["id"] for item in filtered.json()["data"]["content"]}
    assert filtered_ids == {posted.id}

    invalid = client.get("/v1/proposal?status=INVALID", headers=auth_headers)
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.scenario("PROPOSAL-TS-002")
def test_list_public_orders_by_latest_creation_time(client, db, factory, auth_headers, sample_user):
    """홈 화면은 마감 기한과 무관하게 최신 게시글이 최상단에 온다."""
    oldest = factory.proposal(sample_user.id, ProposalStatus.POSTED, "oldest")
    middle = factory.proposal(sample_user.id, ProposalStatus.POSTED, "middle")
    newest = factory.proposal(sample_user.id, ProposalStatus.POSTED, "newest")

    # 최신 글일수록 마감이 멀도록 배치해 deadline 정렬이 남아 있으면 실패하게 한다.
    for proposal, days in ((oldest, 1), (middle, 2), (newest, 3)):
        proposal.deadline = datetime.now(timezone.utc) + timedelta(days=days)
        proposal.meeting_at = proposal.deadline
    db.commit()

    response = client.get("/v1/proposal", headers=auth_headers)

    assert response.status_code == 200
    ordered_ids = [item["id"] for item in response.json()["data"]["content"]]
    assert ordered_ids[:3] == [newest.id, middle.id, oldest.id]


@pytest.mark.scenario("PROPOSAL-TS-003")
def test_detail_returns_proposal_regardless_of_status(client, db, factory, auth_headers, sample_user):
    sample_user.level = 2
    db.commit()
    holding = factory.proposal(sample_user.id, ProposalStatus.HOLDING)
    cancelled = factory.proposal(sample_user.id, ProposalStatus.CANCELLED)

    holding_response = client.get(f"/v1/proposal/{holding.id}", headers=auth_headers)
    assert holding_response.status_code == 200
    holding_data = holding_response.json()["data"]
    assert holding_data["status"] == "HOLDING"
    assert holding_data["ordererId"] == sample_user.id
    assert holding_data["ordererName"] == sample_user.name
    assert holding_data["ordererLevel"] == 2
    assert holding_data["openChatUrl"] is None
    assert holding_data["offers"] == []

    cancelled_response = client.get(f"/v1/proposal/{cancelled.id}", headers=auth_headers)
    assert cancelled_response.status_code == 200
    data = cancelled_response.json()["data"]
    assert data["status"] == "CANCELLED"
    assert data["matchedAt"] is None
    assert data["runnerConfirmedAt"] is None
    assert data["ordererConfirmedAt"] is None
    assert "deliveryReportedAt" not in data
    assert "receivedConfirmedAt" not in data
    assert data["openChatUrl"] is None
    assert data["offers"] == []


@pytest.mark.scenario("PROPOSAL-TS-004")
def test_detail_returns_state_timestamps_when_matched(client, db, factory, auth_headers, sample_user):
    runner = factory.user("01099990003", name="Matched Runner")
    runner.level = 5
    db.commit()
    proposal = factory.proposal(sample_user.id, ProposalStatus.MATCHED)
    proposal.matched_at = datetime.now(timezone.utc)
    offer = Offer(proposal_id=proposal.id, runner_id=runner.id, status=OfferStatus.ACCEPTED)
    db.add(offer)
    db.commit()
    db.refresh(proposal)

    response = client.get(f"/v1/proposal/{proposal.id}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["matchedAt"] is not None
    assert data["runnerConfirmedAt"] is None
    assert data["ordererConfirmedAt"] is None
    assert "deliveryReportedAt" not in data
    assert "receivedConfirmedAt" not in data
    assert data["openChatUrl"] is None
    assert data["ordererId"] == sample_user.id
    assert "missionId" not in data
    assert len(data["offers"]) == 1
    assert data["offers"][0]["id"] == offer.id
    assert data["offers"][0]["runnerName"] == "Matched Runner"
    assert data["offers"][0]["runnerLevel"] == 5


@pytest.mark.scenario("PROPOSAL-TS-005")
def test_detail_returns_open_chat_url_only_to_matched_participants(client, db, factory, auth_headers, sample_user):
    """오픈채팅방 URL은 관리자가 입금 확인 때 요청에 저장한 값을 매칭 당사자에게만 내려준다."""
    runner = factory.user("01055550004", name="Chat Runner")
    stranger = factory.user("01055550005", name="Chat Stranger")
    proposal = factory.proposal(sample_user.id, ProposalStatus.MATCHED)
    proposal.open_chat_url = "https://open.kakao.com/o/example"
    offer = Offer(proposal_id=proposal.id, runner_id=runner.id, status=OfferStatus.ACCEPTED)
    offer.accepted_at = datetime.now(timezone.utc)
    proposal.matched_at = offer.accepted_at
    db.add(offer)
    db.commit()

    orderer_response = client.get(f"/v1/proposal/{proposal.id}", headers=auth_headers)
    runner_response = client.get(f"/v1/proposal/{proposal.id}", headers=factory.headers_for(runner))
    stranger_response = client.get(f"/v1/proposal/{proposal.id}", headers=factory.headers_for(stranger))

    assert orderer_response.status_code == 200
    assert runner_response.status_code == 200
    assert stranger_response.status_code == 200
    assert orderer_response.json()["data"]["openChatUrl"] == "https://open.kakao.com/o/example"
    assert runner_response.json()["data"]["openChatUrl"] == "https://open.kakao.com/o/example"
    assert stranger_response.json()["data"]["openChatUrl"] is None


@pytest.mark.scenario("PROPOSAL-TS-006")
def test_detail_masks_open_chat_url_before_matched_status(client, db, factory, auth_headers, sample_user):
    runner = factory.user("01055550006", name="Waiting Chat Runner")
    proposal = factory.proposal(sample_user.id, ProposalStatus.OFFERED)
    proposal.open_chat_url = "https://open.kakao.com/o/example"
    offer = Offer(proposal_id=proposal.id, runner_id=runner.id, status=OfferStatus.WAITING)
    db.add(offer)
    db.commit()

    response = client.get(f"/v1/proposal/{proposal.id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"]["openChatUrl"] is None


@pytest.mark.scenario("PROPOSAL-TS-007")
def test_list_own_returns_only_current_user_with_offers_and_multi_status_filter(client, db, factory, auth_headers, sample_user):
    other_user = factory.user(name="Old Offer Runner")
    own_posted = factory.proposal(sample_user.id, ProposalStatus.POSTED)
    own_holding = factory.proposal(sample_user.id, ProposalStatus.HOLDING)
    own_cancelled = factory.proposal(sample_user.id, ProposalStatus.CANCELLED)
    factory.proposal(other_user.id, ProposalStatus.POSTED)

    old_offer = Offer(
        proposal_id=own_posted.id,
        runner_id=other_user.id,
        status=OfferStatus.WAITING,
    )
    new_offer = Offer(
        proposal_id=own_posted.id,
        runner_id=factory.user("01099990001", name="New Offer Runner").id,
        status=OfferStatus.REJECTED,
    )
    db.add_all([old_offer, new_offer])
    db.commit()

    response = client.get("/v1/proposal/own?status=POSTED&status=CANCELLED", headers=auth_headers)
    assert response.status_code == 200
    items = response.json()["data"]["content"]
    assert {item["id"] for item in items} == {own_posted.id, own_cancelled.id}
    posted_item = next(item for item in items if item["id"] == own_posted.id)
    assert posted_item["ordererId"] == sample_user.id
    assert posted_item["ordererName"] == sample_user.name
    assert posted_item["ordererLevel"] == sample_user.level
    assert posted_item["offerCount"] == 2
    assert [offer["id"] for offer in posted_item["offers"]] == [new_offer.id, old_offer.id]
    assert [offer["runnerName"] for offer in posted_item["offers"]] == ["New Offer Runner", "Old Offer Runner"]

    all_own_response = client.get("/v1/proposal/own", headers=auth_headers)
    assert {item["id"] for item in all_own_response.json()["data"]["content"]} == {
        own_posted.id,
        own_holding.id,
        own_cancelled.id,
    }


@pytest.mark.scenario("PROPOSAL-TS-008")
def test_list_own_orders_by_badge_then_latest(client, db, factory, auth_headers, sample_user):
    """내 활동 - 요청은 배지 순으로 묶이고, 같은 배지 안에서는 최신순이다."""
    # 생성 순서와 배지 순서를 서로 어긋나게 하고, created_at도 id 순서와 일부러 뒤집어
    # 배지 순 정렬과 created_at 정렬이 각각 제 역할을 하는지 본다.
    base = datetime.now(timezone.utc) - timedelta(hours=3)
    same_deadline = datetime.now(timezone.utc) + timedelta(days=1)
    rows = [
        ("미입금-이전", ProposalStatus.HOLDING, 10),
        ("취소-이전", ProposalStatus.CANCELLED, 20),
        ("진행중-이전", ProposalStatus.MATCHED, 30),
        ("완료-이전", ProposalStatus.ALL_COMPLETED, 40),
        ("대기중-최신", ProposalStatus.POSTED, 90),
        ("미입금-최신", ProposalStatus.HOLDING, 60),
        ("분쟁중", ProposalStatus.DISPUTED, 70),
        ("취소-신고", ProposalStatus.REPORTED, 80),
        ("대기중-이전", ProposalStatus.OFFERED, 50),
        ("취소-환불완료", ProposalStatus.REFUNDED, 100),
        ("진행중-최신", ProposalStatus.ORDER_COMPLETED, 110),
        ("완료-최신", ProposalStatus.ALL_COMPLETED, 120),
    ]
    for title, status, minutes in rows:
        proposal = factory.proposal(sample_user.id, status, title)
        proposal.created_at = base + timedelta(minutes=minutes)
        # deadline이 정렬에 끼어들지 않도록 모두 같은 값으로 맞춘다.
        proposal.deadline = same_deadline
        proposal.meeting_at = same_deadline
    db.commit()

    response = client.get("/v1/proposal/own", headers=auth_headers)

    assert response.status_code == 200
    ordered_titles = [item["title"] for item in response.json()["data"]["content"]]
    assert ordered_titles == [
        "미입금-최신", "미입금-이전",
        "대기중-최신", "대기중-이전",
        "진행중-최신", "진행중-이전",
        "분쟁중",
        "완료-최신", "완료-이전",
        "취소-환불완료", "취소-신고", "취소-이전",
    ]


@pytest.mark.scenario("PROPOSAL-TS-009")
def test_create_proposal_validates_contract_and_stores_holding(client, db, factory, auth_headers, sample_user):
    db.add(
        SettlementAccount(
            user_id=sample_user.id,
            bank_name="국민은행",
            account_holder=sample_user.name,
            encrypted_account_number="123456789012",
            masked_account_number="********9012",
        )
    )
    db.commit()
    response = client.post("/v1/proposal", json=proposal_payload(), headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["message"] == "요청이 등록되었습니다."
    assert body["data"]["status"] == "HOLDING"
    assert set(body["data"]) == {"id", "title", "content", "deadline", "errandFee", "status"}

    proposal = db.query(Proposal).filter(Proposal.id == body["data"]["id"]).one()
    assert proposal.orderer_id == sample_user.id
    assert proposal.status == ProposalStatus.HOLDING


@pytest.mark.scenario("PROPOSAL-TS-010")
def test_create_proposal_requires_settlement_account(client, auth_headers):
    response = client.post("/v1/proposal", json=proposal_payload(), headers=auth_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SETTLEMENT_ACCOUNT_REQUIRED"


@pytest.mark.scenario("PROPOSAL-TS-011")
def test_create_proposal_validation_errors(client, factory, auth_headers, sample_user):
    # 정산 계좌가 없으면 SETTLEMENT_ACCOUNT_REQUIRED(409)가 먼저 반환되므로 계좌를 준비한다.
    factory.settlement_account(sample_user)
    cases = [
        (proposal_payload(title=" "), "VALIDATION_ERROR"),
        (proposal_payload(content=" "), "VALIDATION_ERROR"),
        (proposal_payload(title="가" * 51), "VALIDATION_ERROR"),
        (proposal_payload(content="가" * 501), "VALIDATION_ERROR"),
        (proposal_payload(deadline="not-a-datetime"), "INVALID_DATE_TIME_FORMAT"),
        (proposal_payload(deadline="2026-01-01T00:00:00"), "INVALID_DATE_TIME_FORMAT"),
        (
            proposal_payload(deadline=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat()),
            "PROPOSAL_DEADLINE_INVALID",
        ),
        (proposal_payload(errandFee=999), "PROPOSAL_ERRAND_FEE_INVALID"),
    ]

    for payload, expected_code in cases:
        response = client.post("/v1/proposal", json=payload, headers=auth_headers)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == expected_code


@pytest.mark.scenario("PROPOSAL-TS-012")
def test_update_proposal_author_and_status_rules(client, db, factory, auth_headers, sample_user):
    other_user = factory.user()
    holding = factory.proposal(sample_user.id, ProposalStatus.HOLDING)
    posted = factory.proposal(sample_user.id, ProposalStatus.POSTED)
    offered = factory.proposal(sample_user.id, ProposalStatus.OFFERED)
    matched = factory.proposal(sample_user.id, ProposalStatus.MATCHED)
    cancelled = factory.proposal(sample_user.id, ProposalStatus.CANCELLED)

    forbidden = client.put(f"/v1/proposal/{holding.id}", json=proposal_payload(), headers=factory.headers_for(other_user))
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"

    for editable in [holding, posted]:
        response = client.put(
            f"/v1/proposal/{editable.id}",
            json=proposal_payload(title="수정된 제목"),
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["message"] == "요청이 수정되었습니다."
        assert response.json()["data"]["title"] == "수정된 제목"
        db.refresh(editable)
        assert editable.status == ProposalStatus.HOLDING
        assert editable.meeting_at == editable.deadline

    for not_editable in [offered, matched, cancelled]:
        response = client.put(f"/v1/proposal/{not_editable.id}", json=proposal_payload(), headers=auth_headers)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "PROPOSAL_NOT_EDITABLE"

    missing = client.put("/v1/proposal/999999", json=proposal_payload(), headers=auth_headers)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PROPOSAL_NOT_FOUND"


@pytest.mark.scenario("PROPOSAL-TS-013")
def test_cancel_proposal_author_status_rules_and_rejects_waiting_offers(client, db, factory, auth_headers, sample_user):
    other_user = factory.user()
    holding = factory.proposal(sample_user.id, ProposalStatus.HOLDING)
    posted = factory.proposal(sample_user.id, ProposalStatus.POSTED)
    offered = factory.proposal(sample_user.id, ProposalStatus.OFFERED)
    matched = factory.proposal(sample_user.id, ProposalStatus.MATCHED)
    cancelled = factory.proposal(sample_user.id, ProposalStatus.CANCELLED)

    waiting_offer = Offer(
        proposal_id=offered.id,
        runner_id=other_user.id,
        status=OfferStatus.WAITING,
    )
    cancelled_offer = Offer(
        proposal_id=offered.id,
        runner_id=factory.user("01099990002").id,
        status=OfferStatus.REJECTED,
    )
    db.add_all([waiting_offer, cancelled_offer])
    db.commit()

    forbidden = client.post(f"/v1/proposal/{holding.id}/cancel", headers=factory.headers_for(other_user))
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"

    for cancellable in [holding, posted, offered]:
        response = client.post(f"/v1/proposal/{cancellable.id}/cancel", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["message"] == "요청이 취소되었습니다."
        expected_status = "CANCELLED" if cancellable.id == holding.id else "REFUND_PENDING"
        assert response.json()["data"]["status"] == expected_status

    refunds = db.query(Refund).order_by(Refund.proposal_id).all()
    assert [refund.proposal_id for refund in refunds] == [holding.id, posted.id, offered.id]
    assert {refund.reason for refund in refunds} == {RefundReason.USER_CANCELLED.value}
    # 입금 확인 전 취소는 실제 입금 여부를 모르므로 관리자 대조 대기로 남는다.
    statuses = {refund.proposal_id: refund.status for refund in refunds}
    assert statuses[holding.id] == RefundStatus.REVIEW.value
    assert statuses[posted.id] == RefundStatus.PENDING.value
    assert statuses[offered.id] == RefundStatus.PENDING.value

    db.refresh(waiting_offer)
    db.refresh(cancelled_offer)
    assert waiting_offer.status == OfferStatus.REJECTED
    assert cancelled_offer.status == OfferStatus.REJECTED
    for cancelled_proposal in [holding, posted, offered]:
        db.refresh(cancelled_proposal)
        assert cancelled_proposal.matched_at is None
        assert cancelled_proposal.runner_confirmed_at is None
        assert cancelled_proposal.orderer_confirmed_at is None
        assert cancelled_proposal.disputed_at is None
        assert cancelled_proposal.resolved_at is None
    assert waiting_offer.accepted_at is None
    assert waiting_offer.runner_confirmed_at is None
    assert waiting_offer.orderer_confirmed_at is None
    assert waiting_offer.disputed_at is None
    assert waiting_offer.resolved_at is None

    for not_cancellable in [matched, cancelled]:
        response = client.post(f"/v1/proposal/{not_cancellable.id}/cancel", headers=auth_headers)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "PROPOSAL_NOT_CANCELLABLE"


@pytest.mark.scenario("PROPOSAL-TS-014")
def test_confirm_received_marks_proposal_completed_without_finishing_offer(client, db, factory, auth_headers, sample_user):
    runner = factory.user("01055550001")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)

    response = client.post(f"/v1/proposal/{proposal.id}/confirm-received", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["message"] == "완료 확인되었습니다."
    assert response.json()["data"]["status"] == "ORDER_COMPLETED"
    assert response.json()["data"]["ordererId"] == sample_user.id
    assert response.json()["data"]["ordererConfirmedAt"] is not None
    assert response.json()["data"]["runnerConfirmedAt"] is None
    assert "receivedConfirmedAt" not in response.json()["data"]
    assert "deliveryReportedAt" not in response.json()["data"]
    db.refresh(proposal)
    db.refresh(offer)
    assert proposal.status == ProposalStatus.ORDER_COMPLETED
    assert offer.status == OfferStatus.ACCEPTED
    assert proposal.orderer_confirmed_at is not None
    assert offer.orderer_confirmed_at is not None
    assert proposal.runner_confirmed_at is None
    assert offer.runner_confirmed_at is None
    assert proposal.disputed_at is None
    assert offer.disputed_at is None
    assert proposal.resolved_at is None
    assert offer.resolved_at is None


@pytest.mark.scenario("PROPOSAL-TS-015")
def test_confirm_received_creates_meeting_confirmed_notification_for_runner(client, db, factory, auth_headers, sample_user):
    runner = factory.user("01055550031")
    runner.alarm_enabled = True
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    db.commit()

    response = client.post(f"/v1/proposal/{proposal.id}/confirm-received", headers=auth_headers)

    assert response.status_code == 200
    notification = notification_for(db, runner.id, NotificationType.MEETING_CONFIRMED, offer.id)
    assert notification.title == "행님이 임무 완료를 확인했어요! 🤝"
    assert notification.body == "행님이 임무 완료를 확인했어요. 회원님도 앱에서 임무 완료를 눌러주시면 정산이 바로 진행돼요!"
    assert notification.status == NotificationStatus.PENDING
    assert notification.related_entity_type == "offer"
    assert json.loads(notification.data) == {"offer_id": offer.id, "proposal_id": proposal.id}
    assert notification_count(db, sample_user.id, NotificationType.EXECUTION_COMPLETED, offer.id) == 0
    assert notification_count(db, runner.id, NotificationType.EXECUTION_COMPLETED, offer.id) == 0


@pytest.mark.scenario("PROPOSAL-TS-016")
def test_confirm_received_after_runner_completion_marks_both_all_completed(client, db, factory, auth_headers, sample_user):
    runner = factory.user("01055550002")
    sample_user.level = 6
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.RUNNER_COMPLETED)
    proposal.runner_confirmed_at = datetime.now(timezone.utc)
    offer.runner_confirmed_at = proposal.runner_confirmed_at
    db.commit()

    response = client.post(f"/v1/proposal/{proposal.id}/confirm-received", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ALL_COMPLETED"
    assert response.json()["data"]["ordererLevel"] == 6
    assert response.json()["data"]["offers"][0]["runnerLevel"] == 1
    db.refresh(proposal)
    db.refresh(offer)
    db.refresh(runner)
    db.refresh(sample_user)
    assert proposal.status == ProposalStatus.ALL_COMPLETED
    assert offer.status == OfferStatus.ALL_COMPLETED
    assert runner.level == 1
    assert sample_user.level == 6
    assert proposal.runner_confirmed_at is not None
    assert offer.runner_confirmed_at is not None
    assert proposal.orderer_confirmed_at is not None
    assert offer.orderer_confirmed_at is not None
    assert proposal.disputed_at is None
    assert offer.disputed_at is None
    assert proposal.resolved_at is None
    assert offer.resolved_at is None


@pytest.mark.scenario("PROPOSAL-TS-017")
def test_confirm_received_after_runner_completion_creates_execution_completed_notifications(
    client,
    db,
    factory,
    auth_headers,
    sample_user,
):
    sample_user.alarm_enabled = True
    runner = factory.user("01055550032")
    runner.alarm_enabled = True
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.RUNNER_COMPLETED)
    proposal.runner_confirmed_at = datetime.now(timezone.utc)
    offer.runner_confirmed_at = proposal.runner_confirmed_at
    db.commit()

    response = client.post(f"/v1/proposal/{proposal.id}/confirm-received", headers=auth_headers)

    assert response.status_code == 200
    orderer_completed_notification = notification_for(db, sample_user.id, NotificationType.EXECUTION_COMPLETED, offer.id)
    runner_completed_notification = notification_for(db, runner.id, NotificationType.EXECUTION_COMPLETED, offer.id)
    assert notification_count(db, runner.id, NotificationType.MEETING_CONFIRMED, offer.id) == 0
    assert orderer_completed_notification.status == NotificationStatus.PENDING
    assert runner_completed_notification.status == NotificationStatus.PENDING
    for completed_notification in (orderer_completed_notification, runner_completed_notification):
        assert completed_notification.title == "임무 수행 완료! 수고하셨어요 🎊"
        assert completed_notification.body == "양측 모두 임무 완료를 확인했어요. 성공적으로 임무 수행이 완료됐습니다!"
    assert json.loads(orderer_completed_notification.data) == {"offer_id": offer.id, "proposal_id": proposal.id}
    assert json.loads(runner_completed_notification.data) == {"offer_id": offer.id, "proposal_id": proposal.id}


@pytest.mark.scenario("PROPOSAL-TS-018")
def test_raise_proposal_dispute_updates_both_statuses_and_timestamps(client, db, factory, auth_headers, sample_user):
    runner = factory.user("01055550003")
    runner.alarm_enabled = True
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    offer.accepted_at = datetime.now(timezone.utc)
    proposal.matched_at = offer.accepted_at
    factory.mission(proposal, offer)
    question = dispute_question(DisputeSurveyTargetType.ORDER)
    db.add(question)
    db.commit()

    response = client.post(
        f"/v1/proposal/{proposal.id}/dispute",
        json={"reasonQuestionId": question.id, "detailReason": "물품 상태 불량"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "DISPUTED"
    assert data["disputedAt"] is not None
    db.refresh(proposal)
    db.refresh(offer)
    assert proposal.status == ProposalStatus.DISPUTED
    assert offer.status == OfferStatus.DISPUTED
    assert proposal.disputed_at is not None
    assert offer.disputed_at is not None
    assert proposal.resolved_at is None
    assert offer.resolved_at is None
    evidence = (
        db.query(DisputeEvidence)
        .filter(
            DisputeEvidence.proposal_id == proposal.id,
            DisputeEvidence.offer_id == offer.id,
            DisputeEvidence.actor_id == sample_user.id,
        )
        .one()
    )
    assert evidence.survey_question_id == question.id
    assert evidence.reason == "물품 상태 불량"
    notification = (
        db.query(Notification)
        .filter(
            Notification.user_id == runner.id,
            Notification.notification_type == NotificationType.DISPUTE_RAISED,
            Notification.related_entity_id == offer.id,
        )
        .one()
    )
    assert notification.related_entity_type == "offer"
    assert "행님이 분쟁을 접수" in notification.body


@pytest.mark.scenario("PROPOSAL-TS-019")
def test_raise_proposal_dispute_rejects_invalid_survey_question(client, db, factory, auth_headers, sample_user):
    runner = factory.user("01055550033")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    offer.accepted_at = datetime.now(timezone.utc)
    runner_question = dispute_question(DisputeSurveyTargetType.RUNNER)
    inactive_order_question = dispute_question(DisputeSurveyTargetType.ORDER, display_order=2, is_active=False)
    db.add_all([runner_question, inactive_order_question])
    db.commit()

    wrong_target = client.post(
        f"/v1/proposal/{proposal.id}/dispute",
        json={"reasonQuestionId": runner_question.id, "detailReason": "꼬붕 질문은 불가"},
        headers=auth_headers,
    )
    assert wrong_target.status_code == 400
    assert wrong_target.json()["error"]["code"] == "VALIDATION_ERROR"

    inactive = client.post(
        f"/v1/proposal/{proposal.id}/dispute",
        json={"reasonQuestionId": inactive_order_question.id, "detailReason": "비활성 질문은 불가"},
        headers=auth_headers,
    )
    assert inactive.status_code == 400
    assert inactive.json()["error"]["code"] == "VALIDATION_ERROR"

    missing_reason = client.post(
        f"/v1/proposal/{proposal.id}/dispute",
        json={"detailReason": "질문 없음"},
        headers=auth_headers,
    )
    assert missing_reason.status_code == 400
    assert missing_reason.json()["error"]["code"] == "VALIDATION_ERROR"

    blank_detail = client.post(
        f"/v1/proposal/{proposal.id}/dispute",
        json={"reasonQuestionId": inactive_order_question.id, "detailReason": "   "},
        headers=auth_headers,
    )
    assert blank_detail.status_code == 400
    assert blank_detail.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.scenario("PROPOSAL-TS-020")
def test_raise_proposal_dispute_requires_detail_only_for_etc_reason(client, db, factory, auth_headers, sample_user):
    """사유는 필수이고, 기타 사유를 고를 때만 상세 사유가 필수다. 신고·탈퇴와 같은 정책이다."""
    runner = factory.user("01055550035")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    offer.accepted_at = datetime.now(timezone.utc)
    factory.mission(proposal, offer)
    plain_question = dispute_question(DisputeSurveyTargetType.ORDER)
    etc_question = dispute_question(
        DisputeSurveyTargetType.ORDER,
        question_text="기타",
        display_order=2,
        requires_detail=True,
    )
    db.add_all([plain_question, etc_question])
    db.commit()

    missing_detail = client.post(
        f"/v1/proposal/{proposal.id}/dispute",
        json={"reasonQuestionId": etc_question.id},
        headers=auth_headers,
    )
    assert missing_detail.status_code == 400
    assert missing_detail.json()["error"]["code"] == "VALIDATION_ERROR"
    assert missing_detail.json()["error"]["details"] == "detailReason"

    # 기타가 아닌 사유는 상세 사유 없이 접수된다.
    response = client.post(
        f"/v1/proposal/{proposal.id}/dispute",
        json={"reasonQuestionId": plain_question.id},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "DISPUTED"
    evidence = db.query(DisputeEvidence).filter(DisputeEvidence.proposal_id == proposal.id).one()
    assert evidence.survey_question_id == plain_question.id
    assert evidence.reason is None


@pytest.mark.scenario("PROPOSAL-TS-021")
def test_raise_proposal_dispute_accepts_etc_reason_with_detail(client, db, factory, auth_headers, sample_user):
    runner = factory.user("01055550036")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    offer.accepted_at = datetime.now(timezone.utc)
    factory.mission(proposal, offer)
    etc_question = dispute_question(DisputeSurveyTargetType.ORDER, question_text="기타", requires_detail=True)
    db.add(etc_question)
    db.commit()

    response = client.post(
        f"/v1/proposal/{proposal.id}/dispute",
        json={"reasonQuestionId": etc_question.id, "detailReason": "연락이 되지 않아요"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    evidence = db.query(DisputeEvidence).filter(DisputeEvidence.proposal_id == proposal.id).one()
    assert evidence.survey_question_id == etc_question.id
    assert evidence.reason == "연락이 되지 않아요"


@pytest.mark.scenario("PROPOSAL-TS-022")
def test_raise_proposal_dispute_rejects_all_completed(client, db, factory, auth_headers, sample_user):
    runner = factory.user("01055550004")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.ALL_COMPLETED, OfferStatus.ALL_COMPLETED)
    proposal.disputed_at = None
    offer.disputed_at = None
    question = dispute_question(DisputeSurveyTargetType.ORDER)
    db.add(question)
    db.commit()

    response = client.post(
        f"/v1/proposal/{proposal.id}/dispute",
        json={"reasonQuestionId": question.id, "detailReason": "완료 후 분쟁"},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROPOSAL_NOT_UPDATABLE"
    db.refresh(proposal)
    db.refresh(offer)
    assert proposal.status == ProposalStatus.ALL_COMPLETED
    assert offer.status == OfferStatus.ALL_COMPLETED
    assert proposal.disputed_at is None
    assert offer.disputed_at is None


@pytest.mark.scenario("PROPOSAL-TS-023")
def test_proposal_model_contract(db):
    table = inspect(db.bind).get_columns("proposals")
    columns = {column["name"]: column for column in table}
    assert columns["orderer_id"]["nullable"] is False
    assert columns["title"]["nullable"] is False
    assert columns["content"]["nullable"] is False
    assert columns["deadline"]["nullable"] is False
    assert columns["errand_fee"]["nullable"] is False
    assert columns["meeting_at"]["nullable"] is False
    assert columns["item_price"]["nullable"] is False
    assert columns["deposit"]["nullable"] is False
    assert {status.value for status in ProposalStatus} == {
        "HOLDING",
        "POSTED",
        "OFFERED",
        "MATCHED",
        "ORDER_COMPLETED",
        "ALL_COMPLETED",
        "DISPUTED",
        "REFUND_PENDING",
        "REFUNDED",
        "REPORTED",
        "CANCELLED",
    }
    foreign_keys = inspect(db.bind).get_foreign_keys("proposals")
    assert foreign_keys == []
