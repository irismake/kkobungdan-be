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
