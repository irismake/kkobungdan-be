"""채팅 단위 테스트 (DB 없이 서비스·도메인 규칙 검증).

시나리오 정본: docs/domains/chat/test-scenarios.md 의 CHAT-TS-*
TDD 흐름: docs/design-docs/tdd-workflow.md
"""

import pytest


# ------------------------------------------------------------------ 채팅 내용 검증 (CHAT-REQ-003, 006)

# 화면에 한 글자로 보이지만 여러 코드 포인트로 이루어진 글자들 (Swift String.count 기준 1글자)
FAMILY_EMOJI = "\U0001F468‍\U0001F469‍\U0001F467‍\U0001F466"  # 👨‍👩‍👧‍👦
FLAG_KR = "\U0001F1F0\U0001F1F7"  # 🇰🇷
THUMBS_UP_SKIN_TONE = "\U0001F44D\U0001F3FD"  # 👍🏽
HANGUL_JAMO = "각"  # 조합형 "각"


@pytest.mark.scenario("CHAT-TS-009")
@pytest.mark.parametrize("glyph", [FAMILY_EMOJI, FLAG_KR, THUMBS_UP_SKIN_TONE, HANGUL_JAMO, "가", "a"])
def test_content_length_counts_visible_characters_up_to_500(glyph: str) -> None:
    from app.services.chat.content import count_characters, validate_message_content

    assert count_characters(glyph) == 1
    assert count_characters(glyph * 500) == 500

    assert validate_message_content(glyph * 500) == glyph * 500
    with pytest.raises(ValueError):
        validate_message_content(glyph * 501)


@pytest.mark.scenario("CHAT-TS-080")
def test_content_rejects_blank_and_accepts_text_with_surrounding_spaces() -> None:
    from app.services.chat.content import validate_message_content

    for blank in ["", " ", "   ", "\n", "\n\n", " \n\t \r\n ", "　"]:
        with pytest.raises(ValueError):
            validate_message_content(blank)

    # 앞뒤 공백이 있어도 글자가 하나라도 있으면 통과하고, 내용은 그대로 둔다.
    assert validate_message_content("  안녕하세요  ") == "  안녕하세요  "
    assert validate_message_content("\n네\n") == "\n네\n"


# ------------------------------------------------------------------ 채팅방 상태 변경 규칙 (CHAT-REQ-007)


@pytest.mark.scenario("CHAT-TS-024")
def test_room_state_rules_follow_the_status_reason_table() -> None:
    from app.models.chat import ChatRoomStatus as S
    from app.models.chat import ChatRoomStatusReason as R
    from app.services.chat.room_status import RoomChange as C
    from app.services.chat.room_status import next_room_state

    expected = {
        C.MATCHED: (S.ACTIVE, None),
        C.NOT_SELECTED: (S.CLOSED, R.NOT_SELECTED),
        C.OFFER_CANCELLED: (S.CLOSED, R.OFFER_CANCELLED),
        C.PROPOSAL_CANCELLED: (S.CLOSED, R.PROPOSAL_CANCELLED),
        C.ADMIN_CANCELLED: (S.CLOSED, R.ADMIN_CANCELLED),
        C.ORDERER_DISPUTED: (S.INACTIVE, R.ORDERER_DISPUTED),
        C.RUNNER_DISPUTED: (S.INACTIVE, R.RUNNER_DISPUTED),
        C.DISPUTE_COMPLETED: (S.CLOSED, R.DISPUTE_COMPLETED),
        C.DISPUTE_FAILED: (S.CLOSED, R.DISPUTE_FAILED),
        C.ALL_CONFIRMED: (S.CLOSED, R.ALL_CONFIRMED),
    }
    for change, state in expected.items():
        assert next_room_state(S.ACTIVE, None, change) == state, change

    # 분쟁 중(INACTIVE)에서는 판정으로만 닫힌다.
    assert next_room_state(S.INACTIVE, R.ORDERER_DISPUTED, C.DISPUTE_FAILED) == (S.CLOSED, R.DISPUTE_FAILED)
    # CLOSED는 다시 바뀌지 않는다 (늦게 온 요청은 무시).
    for change in C:
        assert next_room_state(S.CLOSED, R.NOT_SELECTED, change) == (S.CLOSED, R.NOT_SELECTED)


# ------------------------------------------------------------------ 사건별 시스템 채팅 (CHAT-REQ-021)

ORDERER_SEES = {
    "OFFER_CREATED": "회원님의 요청에 새로운 꼬붕이 생겼어요. 확인해보세요!",
    "MATCHED": "꼬붕을 선택하셨어요! 임무를 바로 시작해보세요.",
    "NOT_SELECTED": "다른 꼬붕과 매칭되어 채팅이 종료됐어요.",
    "OFFER_CANCELLED": "꼬붕이 지원을 취소했어요. 채팅이 자동으로 종료돼요.",
    "RUNNER_COMPLETED": "꼬붕이 임무를 완료했어요. 회원님도 확인해주시면 수행비가 꼬붕에게 전달돼요.",
    "ORDERER_CONFIRMED": "꼬붕의 임무 완료를 기다리고 있어요.",
    "ALL_CONFIRMED": "양측 모두 임무 완료를 확인했어요. 성공적으로 임무 수행이 완료됐습니다!",
    "DISPUTE_RAISED": "분쟁 중인 임무예요. 분쟁이 해결될 때까지 잠시만 기다려 주세요.",
    "DISPUTE_COMPLETED": "임무가 완료됐어요. 정산이 곧 시작돼요.",
    "DISPUTE_FAILED": "종료된 임무예요. 더 이상 진행할 수 없어요.",
    "PROPOSAL_CANCELLED": "요청이 취소되어 채팅이 종료됐어요.",
    "ADMIN_CANCELLED_AFTER_MATCH": "종료된 임무예요. 더 이상 진행할 수 없어요.",
    "PAYOUT_COMPLETED": "꼬붕에게 수행비 15,000원이 입금됐어요.",
    "REFUND_COMPLETED": "행님에게 환불이 완료됐어요.",
}
RUNNER_SEES = {
    **ORDERER_SEES,
    "NOT_SELECTED": "이번엔 선택받지 못했지만 다음 기회가 분명 있을 거예요. 다시 도전해보세요!",
    "OFFER_CANCELLED": "지원을 취소했어요. 채팅이 자동으로 종료돼요.",
    "RUNNER_COMPLETED": "행님의 임무 완료 확인을 기다리고 있어요.",
    "ORDERER_CONFIRMED": "행님이 임무 완료를 확인했어요. 회원님도 앱에서 임무 완료를 눌러주시면 정산이 바로 진행돼요!",
    "OFFER_CREATED": "지원이 정상적으로 접수됐어요. 행님의 선택을 기다려주세요.",
    "MATCHED": "행님이 회원님을 선택했어요.",
    "ALL_CONFIRMED": "양측 모두 임무 완료를 확인했어요. 성공적으로 임무 수행이 완료됐습니다!",
    "PAYOUT_COMPLETED": "15,000원이 회원님 계좌로 입금됐어요. 오늘도 멋진 활동 감사해요!",
}


@pytest.mark.scenario("CHAT-TS-062")
def test_every_system_chat_has_the_wording_from_the_table() -> None:
    from app.models.chat import ChatRole, SystemChatEvent
    from app.services.chat.system_chat import render_system_chat

    assert set(ORDERER_SEES) == {event.value for event in SystemChatEvent}
    payload = {"amount": 15000}
    for event in SystemChatEvent:
        assert render_system_chat(event, payload, ChatRole.ORDERER) == ORDERER_SEES[event.value], event
        assert render_system_chat(event, payload, ChatRole.RUNNER) == RUNNER_SEES[event.value], event


# (안읽음 포함, 푸시) — CHAT-REQ-021 표의 "기존 알림"·"안읽음·푸시" 칸. 지원 이후 기존 알림 수신자도 시스템 푸시 대상이다.
DELIVERY_TABLE = {
    ("OFFER_CREATED", "ORDERER"): (True, True),
    ("OFFER_CREATED", "RUNNER"): (True, True),
    ("MATCHED", "ORDERER"): (True, True),
    ("MATCHED", "RUNNER"): (True, True),
    ("NOT_SELECTED", "ORDERER"): (False, False),
    ("NOT_SELECTED", "RUNNER"): (True, True),
    ("OFFER_CANCELLED", "ORDERER"): (True, True),
    ("OFFER_CANCELLED", "RUNNER"): (True, True),
    ("RUNNER_COMPLETED", "ORDERER"): (True, True),
    ("RUNNER_COMPLETED", "RUNNER"): (True, True),
    ("ORDERER_CONFIRMED", "ORDERER"): (True, True),
    ("ORDERER_CONFIRMED", "RUNNER"): (True, True),
    ("ALL_CONFIRMED", "ORDERER"): (True, True),
    ("ALL_CONFIRMED", "RUNNER"): (True, True),
    ("DISPUTE_COMPLETED", "ORDERER"): (True, True),
    ("DISPUTE_COMPLETED", "RUNNER"): (True, True),
    ("DISPUTE_FAILED", "ORDERER"): (True, True),
    ("DISPUTE_FAILED", "RUNNER"): (True, True),
    ("PROPOSAL_CANCELLED", "ORDERER"): (True, True),
    ("PROPOSAL_CANCELLED", "RUNNER"): (True, True),
    ("ADMIN_CANCELLED_AFTER_MATCH", "ORDERER"): (True, True),
    ("ADMIN_CANCELLED_AFTER_MATCH", "RUNNER"): (True, True),
    ("PAYOUT_COMPLETED", "ORDERER"): (True, True),
    ("PAYOUT_COMPLETED", "RUNNER"): (True, True),
    ("REFUND_COMPLETED", "ORDERER"): (True, True),
    ("REFUND_COMPLETED", "RUNNER"): (True, True),
}


@pytest.mark.scenario("CHAT-TS-063")
def test_unread_and_push_targets_follow_the_table() -> None:
    from app.models.chat import ChatRole, SystemChatEvent
    from app.services.chat.system_chat import system_chat_delivery

    for (event, role), expected in DELIVERY_TABLE.items():
        assert system_chat_delivery(SystemChatEvent(event), ChatRole(role), {}) == expected, (event, role)

    # 분쟁 접수: 접수한 쪽은 안읽음·푸시 포함, 접수당한 쪽도 안읽음·푸시 포함.
    by_orderer = {"raisedBy": "ORDERER"}
    assert system_chat_delivery(SystemChatEvent.DISPUTE_RAISED, ChatRole.ORDERER, by_orderer) == (True, True)
    assert system_chat_delivery(SystemChatEvent.DISPUTE_RAISED, ChatRole.RUNNER, by_orderer) == (True, True)
    by_runner = {"raisedBy": "RUNNER"}
    assert system_chat_delivery(SystemChatEvent.DISPUTE_RAISED, ChatRole.RUNNER, by_runner) == (True, True)
    assert system_chat_delivery(SystemChatEvent.DISPUTE_RAISED, ChatRole.ORDERER, by_runner) == (True, True)


# ------------------------------------------------------------------ 채팅 푸시 재시도 (CHAT-REQ-018, 029)

from datetime import datetime, timedelta  # noqa: E402

PUSH_AT = datetime(2026, 11, 17, 12, 0, 0)


def _push_envelope(occurred_at: datetime):
    from app.services.outbox.envelope import EventEnvelope

    return EventEnvelope(
        event_id="evt-1",
        event_type="chat.message.created",
        aggregate_type="chat_room",
        aggregate_id="1",
        schema_version=1,
        occurred_at=occurred_at,
        payload={"roomId": 1, "messageId": 1, "seq": 3, "type": "USER", "senderId": "u-1", "systemEvent": None},
    )


class _NoSession:
    def __call__(self):
        raise AssertionError("유효 시간이 지난 푸시는 DB를 보지 않는다")


class _NeverSend:
    def send(self, **push):
        raise AssertionError("유효 시간이 지난 푸시는 보내지 않는다")


@pytest.mark.scenario("CHAT-TS-106")
def test_push_older_than_ten_minutes_is_skipped_without_sending() -> None:
    from app.models.outbox import DeliveryStatus
    from app.services.chat.chat_push import ChatPushConsumer
    from app.services.outbox.delivery import execute_delivery

    consumer = ChatPushConsumer(_NoSession(), _NeverSend())
    envelope = _push_envelope(PUSH_AT)

    outcome = execute_delivery(consumer, envelope, attempts=2, now=PUSH_AT + timedelta(minutes=10))

    assert outcome.status == DeliveryStatus.SKIPPED
    assert outcome.skip_reason == "expired"


@pytest.mark.scenario("CHAT-TS-111")
def test_push_retries_five_times_within_ten_minutes_then_dies_with_one_alert() -> None:
    from types import SimpleNamespace

    from app.models.outbox import DeliveryStatus
    from app.services.chat.chat_push import CHAT_PUSH_RETRY_POLICY, ChatPushConsumer
    from app.services.outbox.delivery import alert_dead_delivery, execute_delivery

    assert ChatPushConsumer.name == "chat.push"
    assert ChatPushConsumer.retry_policy == CHAT_PUSH_RETRY_POLICY

    def always_fail(envelope):
        raise RuntimeError("FCM 오류")

    consumer = SimpleNamespace(name="chat.push", retry_policy=CHAT_PUSH_RETRY_POLICY, handle=always_fail)
    envelope = _push_envelope(PUSH_AT)

    now, attempts, gaps = PUSH_AT, 0, []
    while True:
        outcome = execute_delivery(consumer, envelope, attempts, now)
        if outcome.status != DeliveryStatus.FAILED:
            break
        gaps.append(outcome.next_attempt_at - now)
        now, attempts = outcome.next_attempt_at, attempts + 1

    assert gaps == [timedelta(seconds=s) for s in (5, 30, 60, 120, 240)]
    assert outcome.status == DeliveryStatus.DEAD
    assert now < PUSH_AT + timedelta(minutes=10)  # 유효 시간이 먼저 지나 SKIPPED가 되지 않는다

    alerts = []
    sender = SimpleNamespace(send=alerts.append)
    delivery = SimpleNamespace(consumer="chat.push", attempts=6, last_error="FCM 오류", dead_alerted_at=None)
    alert_dead_delivery(delivery, envelope, sender, now)
    alert_dead_delivery(delivery, envelope, sender, now)
    assert len(alerts) == 1


# ------------------------------------------------------------------ 실시간 전달 (CHAT-REQ-016, 029)


class _Hub:
    def __init__(self, connected: bool, fail: bool = False):
        self._connected, self._fail = connected, fail
        self.sent = []

    def is_connected(self, user_id: str) -> bool:
        return self._connected

    def send(self, user_id: str, event: dict) -> int:
        if self._fail:
            raise ConnectionError("WebSocket 전송 오류")
        self.sent.append((user_id, event))
        return 1


@pytest.mark.scenario("CHAT-TS-110")
@pytest.mark.parametrize("hub,reason", [(_Hub(connected=False), "not_connected"), (_Hub(connected=True, fail=True), "send_error")])
def test_realtime_delivery_is_skipped_without_retry_when_nobody_can_receive(hub, reason) -> None:
    from app.models.outbox import DeliveryStatus
    from app.services.chat.chat_realtime import ChatRealtimeConsumer
    from app.services.outbox.delivery import execute_delivery
    from app.services.outbox.envelope import EventEnvelope

    consumer = ChatRealtimeConsumer(_NoSession(), hub)
    assert consumer.name == "chat.realtime"
    assert consumer.retry_policy.max_retries == 0
    envelope = EventEnvelope(
        event_id="evt-2",
        event_type="chat.room.updated",
        aggregate_type="chat_room",
        aggregate_id="1",
        schema_version=1,
        occurred_at=PUSH_AT,
        payload={
            "roomId": 1, "ordererId": "o-1", "runnerId": "r-1", "status": "CLOSED", "statusReason": "OFFER_CANCELLED",
            "proposalStatus": "OFFERED", "offerStatus": "CANCELLED", "version": 3,
        },
    )

    outcome = execute_delivery(consumer, envelope, attempts=0, now=PUSH_AT)

    # SKIPPED는 끝난 전달이라 다시 시도하지 않고, DEAD가 아니라 모니터링 알림도 없다
    assert (outcome.status, outcome.skip_reason) == (DeliveryStatus.SKIPPED, reason)
