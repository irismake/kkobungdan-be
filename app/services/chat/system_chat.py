"""사건별 시스템 채팅 문구 (CHAT-REQ-021).

시스템 채팅은 사건 코드(`system_event`)와 값(`system_payload`)으로 저장하고, 조회할 때 보는 사람의
역할(행님/꼬붕)에 맞는 문구로 만든다. 문구 표는 이 파일 한 곳에 둔다.
"""

from __future__ import annotations

from typing import Any

from app.models.chat import ChatRole, SystemChatEvent


# 사건 → (행님에게 보이는 문구, 꼬붕에게 보이는 문구)
_TEXTS: dict[SystemChatEvent, tuple[str, str]] = {
    SystemChatEvent.OFFER_CREATED: ("지원으로 채팅이 시작됐어요.", "지원으로 채팅이 시작됐어요."),
}


def render_system_chat(event: SystemChatEvent, payload: dict[str, Any] | None, viewer: ChatRole) -> str:
    orderer_text, runner_text = _TEXTS[event]
    text = orderer_text if viewer == ChatRole.ORDERER else runner_text
    return text.format(**(payload or {}))
