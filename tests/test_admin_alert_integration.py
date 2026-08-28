"""관리자 운영 알림: 분쟁 접수와 미션 완료 시 Slack 알림이 나가는지 검증한다."""

from __future__ import annotations

import httpx
import pytest

from app.models.dispute_survey import DisputeSurveyQuestion, DisputeSurveyTargetType
from app.models.mission import MissionStatus
from app.models.offer import OfferStatus
from app.models.proposal import ProposalStatus
from app.services.admin_alert_service import AdminAlert, SlackAdminAlertSender


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


# ------------------------------------------------------------------ 분쟁 접수


def test_runner_dispute_alerts_admin(client, db, factory, sample_user, admin_alerts):
    runner = factory.user("01077770001", name="홍길동")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    mission = factory.mission(proposal, offer)
    question = _survey_question(db, DisputeSurveyTargetType.RUNNER)

    response = client.post(
        f"/v1/offer/{offer.id}/dispute",
        headers=factory.headers_for(runner),
        json={"reasonQuestionId": question.id, "detailReason": "행님이 연락을 받지 않습니다."},
    )

    assert response.status_code == 200
    assert len(admin_alerts.sent) == 1
    text = admin_alerts.texts[0]
    assert "분쟁이 접수됐어요" in text
    assert f"미션 #{mission.id}" in text
    assert "홍길동" in text
    assert "5,000원" in text


def test_orderer_dispute_alerts_admin(client, db, factory, sample_user, admin_alerts):
    runner = factory.user("01077770002")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    factory.mission(proposal, offer)
    question = _survey_question(db, DisputeSurveyTargetType.ORDER)

    response = client.post(
        f"/v1/proposal/{proposal.id}/dispute",
        headers=factory.headers_for(sample_user),
        json={"reasonQuestionId": question.id, "detailReason": "물건을 받지 못했습니다."},
    )

    assert response.status_code == 200
    assert len(admin_alerts.sent) == 1
    assert "분쟁이 접수됐어요" in admin_alerts.texts[0]


def test_sync_does_not_realert_for_already_disputed_mission(db, factory, sample_user):
    """미션이 이미 분쟁중이면 상태 동기화가 다시 알림을 만들지 않는다.

    `mark_disputed`는 no-op이라 호출 여부만으로는 전이를 판별할 수 없다.
    """
    from app.services.admin_alert_outbox import pop_admin_alerts
    from app.services.mission.mission_service import MissionService

    runner = factory.user("01077770003")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.DISPUTED, OfferStatus.DISPUTED)
    factory.mission(proposal, offer, MissionStatus.DISPUTED)

    MissionService.sync_from_offer_and_proposal(db, offer, proposal)

    assert pop_admin_alerts(db) == []


# ------------------------------------------------------------------ 미션 완료


def test_both_side_confirmation_alerts_admin_to_pay(client, db, factory, sample_user, admin_alerts):
    runner = factory.user("01077770004", name="김꼬붕")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.MATCHED, OfferStatus.ACCEPTED)
    mission = factory.mission(proposal, offer)

    client.post(f"/v1/offer/{offer.id}/complete-delivery", headers=factory.headers_for(runner))
    assert admin_alerts.sent == [], "한쪽만 확인한 시점에는 알림이 나가지 않는다"

    client.post(f"/v1/proposal/{proposal.id}/confirm-received", headers=factory.headers_for(sample_user))

    db.refresh(mission)
    assert mission.status == MissionStatus.COMPLETED.value
    assert len(admin_alerts.sent) == 1
    text = admin_alerts.texts[0]
    assert "수행비 입금이 필요합니다" in text
    assert f"미션 #{mission.id}" in text
    assert "김꼬붕" in text
    assert "5,000원" in text


def test_admin_mission_resolve_completed_alerts_to_pay(client, factory, sample_user, admin_headers, admin_alerts):
    runner = factory.user("01077770005")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.DISPUTED, OfferStatus.DISPUTED)
    mission = factory.mission(proposal, offer, MissionStatus.DISPUTED)

    response = client.post(
        f"/v1/admin/missions/{mission.id}/resolve",
        json={"resolution": "COMPLETED"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert len(admin_alerts.sent) == 1
    assert "수행비 입금이 필요합니다" in admin_alerts.texts[0]


def test_admin_mission_resolve_failed_does_not_alert(client, factory, sample_user, admin_headers, admin_alerts):
    runner = factory.user("01077770006")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.DISPUTED, OfferStatus.DISPUTED)
    mission = factory.mission(proposal, offer, MissionStatus.DISPUTED)

    response = client.post(
        f"/v1/admin/missions/{mission.id}/resolve",
        json={"resolution": "FAILED"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert admin_alerts.sent == []


def test_admin_dispute_resolve_completed_alerts_to_pay(client, factory, sample_user, admin_headers, admin_alerts):
    runner = factory.user("01077770007")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.DISPUTED, OfferStatus.DISPUTED)
    factory.mission(proposal, offer, MissionStatus.DISPUTED)
    evidence = factory.dispute_evidence(proposal, offer, sample_user.id)

    response = client.post(
        f"/v1/admin/dispute/{evidence.id}/resolve",
        json={"outcome": "COMPLETED", "adminNote": "꼬붕 과실 없음"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert len(admin_alerts.sent) == 1
    assert "수행비 입금이 필요합니다" in admin_alerts.texts[0]


def test_recording_settlement_does_not_alert(client, factory, sample_user, admin_headers, admin_alerts):
    runner = factory.user("01077770008")
    proposal, offer = factory.execution(sample_user, runner, ProposalStatus.ALL_COMPLETED, OfferStatus.ALL_COMPLETED)
    mission = factory.mission(proposal, offer, MissionStatus.COMPLETED)

    response = client.post(
        f"/v1/admin/missions/{mission.id}/settlement",
        json={"adminId": sample_user.id, "memo": "이체 참조번호 20260827-001"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert admin_alerts.sent == []


# ------------------------------------------------------------------ 발송기 자체


def test_sender_is_noop_without_webhook_url():
    sender = SlackAdminAlertSender(webhook_url=None)

    assert sender.enabled is False
    sender.send(AdminAlert(headline="테스트"))  # 예외 없이 통과해야 한다


def test_sender_posts_text_payload_to_webhook():
    posted: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posted.append({"url": str(request.url), "body": request.read().decode()})
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sender = SlackAdminAlertSender(webhook_url="https://hooks.slack.test/abc", client=client)

    sender.send(AdminAlert(headline="🚨 분쟁", lines=["미션 #1"]))

    assert len(posted) == 1
    assert posted[0]["url"] == "https://hooks.slack.test/abc"
    assert "미션 #1" in posted[0]["body"]


def test_sender_swallows_failure_and_logs(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="slack down")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sender = SlackAdminAlertSender(webhook_url="https://hooks.slack.test/abc", client=client)

    with caplog.at_level("ERROR"):
        sender.send(AdminAlert(headline="🚨 분쟁"))

    assert "관리자 Slack 알림 발송에 실패했습니다" in caplog.text


def test_alert_link_uses_admin_web_base_url(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_web_base_url", "https://admin.example.test/")
    alert = AdminAlert(headline="제목", link_label="열기", link_path="missions/7")

    assert "<https://admin.example.test/missions/7|열기>" in alert.to_text()


def test_alert_omits_link_when_admin_web_base_url_missing(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_web_base_url", None)
    alert = AdminAlert(headline="제목", link_label="열기", link_path="missions/7")

    assert alert.to_text() == "제목"


@pytest.mark.parametrize("amount,expected", [(5000, "5,000원"), (150000, "150,000원")])
def test_fee_is_thousand_separated(amount, expected):
    from app.listeners.admin_alert_listener import _fee

    assert _fee(amount) == expected
