"""지원 전 알림 / 지원 이후 시스템 채팅 계약 회귀 테스트."""
import json

import pytest

from app.models.chat import ChatMessage, ChatMessageType, ChatRoom
from app.models.notification import Notification
from app.models.proposal import ProposalStatus
from app.models.refund import Refund
from tests.test_chat_integration import Journey, FakePushSender, enable_push, run_chat_push, messages, _cause


@pytest.fixture
def journey(client, db, factory, sample_user, admin_headers):
    return Journey(client, db, factory, sample_user, admin_headers)


@pytest.mark.scenario("NOTI-TS-030")
@pytest.mark.parametrize("by", ["user", "admin"])
@pytest.mark.parametrize("alarm", [True, False])
def test_before_offer_cancellation_notification(journey, db, monkeypatch, by, alarm):
    journey.orderer.alarm_enabled = alarm
    db.commit()
    queued = []
    class Worker:
        def flush_pending(self, factory, ids):
            queued.extend(ids)
    for module in ("proposal.proposal_router", "admin.admin_router"):
        monkeypatch.setattr(f"app.api.v1.{module}.get_notification_worker", lambda: Worker())
    result = journey.cancel_proposal() if by == "user" else journey.admin_cancel()
    assert result.status_code == 200
    notice = db.query(Notification).one()
    assert notice.user_id == journey.orderer.id
    assert notice.notification_type == f"proposal_cancelled_by_{by}"
    assert notice.title == "요청이 취소됐어요."
    assert notice.body == ("요청이 취소됐어요." if by == "user" else "관리자에 의해 요청이 취소됐어요.")
    assert json.loads(notice.data) == {"proposal_id": journey.proposal.id}
    assert notice.related_entity_type == "proposal"
    assert notice.related_entity_id == journey.proposal.id
    assert notice.status == ("pending" if alarm else "skipped")
    assert queued == ([notice.id] if alarm else [])
    assert db.query(ChatMessage).count() == 0


@pytest.mark.scenario("NOTI-TS-031")
@pytest.mark.parametrize("alarm", [True, False])
def test_before_offer_refund_notification(journey, db, monkeypatch, alarm):
    journey.orderer.alarm_enabled = alarm
    db.commit()
    assert journey.admin_cancel().status_code == 200
    queued = []
    class Worker:
        def flush_pending(self, factory, ids):
            queued.extend(ids)
    monkeypatch.setattr("app.api.v1.admin.admin_router.get_notification_worker", lambda: Worker())
    journey.refund_complete()
    notice = db.query(Notification).filter(Notification.notification_type == "refund_completed").one()
    assert (notice.title, notice.body) == ("환불이 완료됐어요.", "행님에게 환불이 완료됐어요.")
    assert notice.user_id == journey.orderer.id
    assert json.loads(notice.data) == {"proposal_id": journey.proposal.id}
    assert queued == ([notice.id] if alarm else [])
    assert notice.status == ("pending" if alarm else "skipped")
    assert db.query(ChatMessage).count() == 0
    refund = db.query(Refund).one()
    result = journey.client.post(f"/v1/admin/refund/{refund.id}/complete", headers=journey.admin_headers)
    assert result.status_code == 400
    assert db.query(Notification).filter(Notification.notification_type == "refund_completed").count() == 1


@pytest.mark.scenario("CHAT-TS-112")
def test_before_match_refund_in_existing_rooms(journey, db):
    a = journey.apply("01079000001", "꼬붕 A")
    b = journey.apply("01079000002", "꼬붕 B")
    assert journey.cancel_offer(a).status_code == 204  # 이미 닫힌 방도 환불 안내 포함
    assert journey.cancel_proposal().status_code == 200
    journey.refund_complete()
    from app.services.chat.chat_lifecycle import ChatLifecycle
    ChatLifecycle.on_refund_completed(db, db.query(Refund).one())  # 중복 전달
    db.commit()
    for runner in (a, b):
        room = journey.room(runner)
        assert room.status == "CLOSED"
        chats = messages(journey.client, journey.factory, room.id, runner)
        notices = [m for m in chats if m["systemEvent"] == "REFUND_COMPLETED"]
        assert len(notices) == 1
        assert notices[0]["content"] == "행님에게 환불이 완료됐어요."
    assert db.query(Notification).count() == 0
    enable_push(db, journey.orderer, a, b)
    sender = FakePushSender()
    run_chat_push(sender)
    pushes = [p for p in sender.sent if p["body"] == "행님에게 환불이 완료됐어요."]
    assert len(pushes) == 4
    assert {p["data"]["roomId"] for p in pushes} == {str(journey.room(r).id) for r in (a,b)}


# 2026-11-18 전환 전 listener의 제목·본문을 고정한 스냅샷. 구현의 문구표를 import하지 않는다.
COPY_CASES = [['OFFER_CREATED', 'ORDERER', '누군가 지원했어요! 👀', '회원님의 요청에 새로운 꼬붕이 생겼어요. 확인해보세요!'], ['OFFER_CREATED', 'RUNNER', '지원 완료! ✅', '지원이 정상적으로 접수됐어요. 행님의 선택을 기다려주세요.'], ['MATCHED', 'ORDERER', '임무가 시작됐어요! 🏃', '꼬붕을 선택하셨어요! 임무를 바로 시작해보세요.'], ['MATCHED', 'RUNNER', '선택받으셨어요! 🙌', '행님이 회원님을 선택했어요.'], ['NOT_SELECTED', 'RUNNER', '이번엔 아쉽게 됐어요 😢', '이번엔 선택받지 못했지만 다음 기회가 분명 있을 거예요. 다시 도전해보세요!'], ['RUNNER_COMPLETED', 'ORDERER', '꼬붕이 임무를 완료했어요! 🤝', '꼬붕이 임무를 완료했어요. 회원님도 확인해주시면 수행비가 꼬붕에게 전달돼요.'], ['ORDERER_CONFIRMED', 'RUNNER', '행님이 임무 완료를 확인했어요! 🤝', '행님이 임무 완료를 확인했어요. 회원님도 앱에서 임무 완료를 눌러주시면 정산이 바로 진행돼요!'], ['DISPUTE_RAISED', 'RUNNER', '분쟁이 접수되었어요 🚨', '행님이 분쟁을 접수했어요. 앱에서 내용을 확인해주세요.'], ['DISPUTE_RAISED_BY_RUNNER', 'ORDERER', '분쟁이 접수되었어요 🚨', '꼬붕이 분쟁을 접수했어요. 앱에서 내용을 확인해주세요.'], ['ALL_CONFIRMED', 'ORDERER', '임무 수행 완료! 수고하셨어요 🎊', '양측 모두 임무 완료를 확인했어요. 성공적으로 임무 수행이 완료됐습니다!'], ['ALL_CONFIRMED', 'RUNNER', '임무 수행 완료! 수고하셨어요 🎊', '양측 모두 임무 완료를 확인했어요. 성공적으로 임무 수행이 완료됐습니다!'], ['PAYOUT_COMPLETED', 'RUNNER', '수행비가 입금됐어요! 💰', '5,000원이 회원님 계좌로 입금됐어요. 오늘도 멋진 활동 감사해요!']]


@pytest.mark.scenario("CHAT-TS-113")
@pytest.mark.parametrize("case,role,title,body", COPY_CASES)
def test_system_copy_and_push_replace_notifications(journey, db, case, role, title, body):
    if case == "DISPUTE_RAISED_BY_RUNNER":
        runner = journey.apply("01079000003", "꼬붕")
        journey.accept(runner)
        journey.dispute("RUNNER", runner)
        event = "DISPUTE_RAISED"
    else:
        runner, event = _cause(journey, case)
    room = journey.room(runner)
    viewer = journey.orderer if role == "ORDERER" else runner
    notice = [m for m in messages(journey.client, journey.factory, room.id, viewer) if m["systemEvent"] == event][-1]
    assert (notice["systemTitle"], notice["content"]) == (title, body)
    assert db.query(Notification).count() == 0
    enable_push(db, journey.orderer, runner)
    sender = FakePushSender()
    run_chat_push(sender)
    pushes = [p for p in sender.to(viewer) if p["data"]["messageId"] == str(notice["id"])]
    assert len(pushes) == 1
    assert (pushes[0]["title"], pushes[0]["body"]) == (title, body)
    assert pushes[0]["data"]["type"] == "CHAT"
    assert pushes[0]["data"]["roomId"] == str(room.id)


@pytest.mark.scenario("CHAT-TS-114")
@pytest.mark.parametrize("has_offer", [False, True])
def test_notice_failure_rolls_back_business_change(journey, db, monkeypatch, has_offer):
    from app.services.chat.chat_lifecycle import ChatLifecycle
    from app.services.proposal.proposal_service import ProposalService
    from app.models.outbox import OutboxEvent
    if has_offer:
        journey.apply("01079000004", "꼬붕")
    before_messages = db.query(ChatMessage).count()
    before_events = db.query(OutboxEvent).count()
    def fail(*args, **kwargs):
        raise RuntimeError("안내 저장 실패")
    if has_offer:
        monkeypatch.setattr(ChatLifecycle, "_add_system_chat", fail)
    else:
        monkeypatch.setattr("app.services.notification.proposal_notice.track_created_notification", fail)
    with pytest.raises(RuntimeError, match="안내 저장 실패"):
        ProposalService.cancel(db, journey.proposal.id, journey.orderer.id)
    db.rollback()
    db.refresh(journey.proposal)
    assert journey.proposal.status == (ProposalStatus.OFFERED if has_offer else ProposalStatus.POSTED)
    assert db.query(Notification).count() == 0
    assert db.query(Refund).count() == 0
    assert db.query(ChatMessage).count() == before_messages
    assert db.query(OutboxEvent).count() == before_events
