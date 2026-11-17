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
    "OFFER_CREATED": "지원으로 채팅이 시작됐어요.",
    "MATCHED": "매칭이 완료되어 임무가 시작됐어요.",
    "NOT_SELECTED": "다른 꼬붕과 매칭되어 채팅이 종료됐어요.",
    "OFFER_CANCELLED": "꼬붕이 지원을 취소했어요. 채팅이 자동으로 종료돼요.",
    "RUNNER_COMPLETED": "꼬붕이 임무를 완료했어요. 행님도 임무 완료를 확인해 주세요.",
    "ORDERER_CONFIRMED": "꼬붕의 임무 완료를 기다리고 있어요.",
    "ALL_CONFIRMED": "임무가 완료됐어요. 정산이 곧 시작돼요.",
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
    "NOT_SELECTED": "이번에는 매칭되지 않았어요. 채팅이 자동으로 종료돼요.",
    "OFFER_CANCELLED": "지원을 취소했어요. 채팅이 자동으로 종료돼요.",
    "RUNNER_COMPLETED": "행님의 임무 완료 확인을 기다리고 있어요.",
    "ORDERER_CONFIRMED": "행님이 임무 완료를 확인했어요. 꼬붕도 임무를 완료해 주세요.",
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


# (안읽음 포함, 푸시) — CHAT-REQ-021 표의 "기존 알림"·"안읽음·푸시" 칸. 기존 알림을 받는 사람은 푸시하지 않는다.
DELIVERY_TABLE = {
    ("OFFER_CREATED", "ORDERER"): (True, False),
    ("OFFER_CREATED", "RUNNER"): (True, False),
    ("MATCHED", "ORDERER"): (True, False),
    ("MATCHED", "RUNNER"): (True, False),
    ("NOT_SELECTED", "ORDERER"): (False, False),
    ("NOT_SELECTED", "RUNNER"): (True, False),
    ("OFFER_CANCELLED", "ORDERER"): (True, True),
    ("OFFER_CANCELLED", "RUNNER"): (True, True),
    ("RUNNER_COMPLETED", "ORDERER"): (True, False),
    ("RUNNER_COMPLETED", "RUNNER"): (True, True),
    ("ORDERER_CONFIRMED", "ORDERER"): (True, True),
    ("ORDERER_CONFIRMED", "RUNNER"): (True, False),
    ("ALL_CONFIRMED", "ORDERER"): (True, False),
    ("ALL_CONFIRMED", "RUNNER"): (True, False),
    ("DISPUTE_COMPLETED", "ORDERER"): (True, True),
    ("DISPUTE_COMPLETED", "RUNNER"): (True, True),
    ("DISPUTE_FAILED", "ORDERER"): (True, True),
    ("DISPUTE_FAILED", "RUNNER"): (True, True),
    ("PROPOSAL_CANCELLED", "ORDERER"): (True, True),
    ("PROPOSAL_CANCELLED", "RUNNER"): (True, True),
    ("ADMIN_CANCELLED_AFTER_MATCH", "ORDERER"): (True, True),
    ("ADMIN_CANCELLED_AFTER_MATCH", "RUNNER"): (True, True),
    ("PAYOUT_COMPLETED", "ORDERER"): (True, True),
    ("PAYOUT_COMPLETED", "RUNNER"): (True, False),
    ("REFUND_COMPLETED", "ORDERER"): (True, True),
    ("REFUND_COMPLETED", "RUNNER"): (True, True),
}


@pytest.mark.scenario("CHAT-TS-063")
def test_unread_and_push_targets_follow_the_table() -> None:
    from app.models.chat import ChatRole, SystemChatEvent
    from app.services.chat.system_chat import system_chat_delivery

    for (event, role), expected in DELIVERY_TABLE.items():
        assert system_chat_delivery(SystemChatEvent(event), ChatRole(role), {}) == expected, (event, role)

    # 분쟁 접수: 접수한 쪽은 안읽음·푸시 포함, 접수당한 쪽(기존 알림 받음)은 안읽음만.
    by_orderer = {"raisedBy": "ORDERER"}
    assert system_chat_delivery(SystemChatEvent.DISPUTE_RAISED, ChatRole.ORDERER, by_orderer) == (True, True)
    assert system_chat_delivery(SystemChatEvent.DISPUTE_RAISED, ChatRole.RUNNER, by_orderer) == (True, False)
    by_runner = {"raisedBy": "RUNNER"}
    assert system_chat_delivery(SystemChatEvent.DISPUTE_RAISED, ChatRole.RUNNER, by_runner) == (True, True)
    assert system_chat_delivery(SystemChatEvent.DISPUTE_RAISED, ChatRole.ORDERER, by_runner) == (True, False)
