"""채팅 내용 검증 (CHAT-REQ-003, CHAT-REQ-006).

글자 수는 화면에 보이는 글자(grapheme cluster) 단위로 센다. 앱(Swift `String.count`)과 같은 기준이다.
이모지 조합(가족, 국기, 피부색)이나 조합형 한글도 한 글자로 센다.
"""

from __future__ import annotations

import regex

MAX_MESSAGE_LENGTH = 500

_GRAPHEME = regex.compile(r"\X")


def count_characters(text: str) -> int:
    """화면에 보이는 글자 수를 센다."""
    return len(_GRAPHEME.findall(text))


def validate_message_content(text: str) -> str:
    """채팅·첫 인사 내용을 검증하고 그대로 돌려준다.

    공백·줄바꿈만 있으면 거부하고, 500자를 넘으면 거부한다. 앞뒤 공백은 지우지 않는다.
    Pydantic validator에서 쓰므로 실패는 ValueError로 알린다(400 VALIDATION_ERROR).
    """
    if not text.strip():
        raise ValueError("내용을 입력해주세요.")
    if count_characters(text) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"{MAX_MESSAGE_LENGTH}자 이하로 입력해주세요.")
    return text
