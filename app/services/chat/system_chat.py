"""사건별 시스템 채팅 문구 (CHAT-REQ-021).

시스템 채팅은 사건 코드(`system_event`)와 값(`system_payload`)으로 저장하고, 조회할 때 보는 사람의
역할(행님/꼬붕)에 맞는 문구로 만든다. 문구 표는 이 파일 한 곳에 둔다.
"""

from __future__ import annotations

from typing import Any

from app.models.chat import ChatRole, SystemChatEvent


_FINISHED = "임무가 완료됐어요. 정산이 곧 시작돼요."
_ENDED = "종료된 임무예요. 더 이상 진행할 수 없어요."

# 사건 → (행님에게 보이는 문구, 꼬붕에게 보이는 문구). chat-requirements.md CHAT-REQ-021 표가 정본이다.
_TEXTS: dict[SystemChatEvent, tuple[str, str]] = {
    SystemChatEvent.OFFER_CREATED: ("지원으로 채팅이 시작됐어요.", "지원으로 채팅이 시작됐어요."),
    SystemChatEvent.MATCHED: ("매칭이 완료되어 임무가 시작됐어요.", "매칭이 완료되어 임무가 시작됐어요."),
    SystemChatEvent.NOT_SELECTED: (
        "다른 꼬붕과 매칭되어 채팅이 종료됐어요.",
        "이번에는 매칭되지 않았어요. 채팅이 자동으로 종료돼요.",
    ),
    SystemChatEvent.OFFER_CANCELLED: (
        "꼬붕이 지원을 취소했어요. 채팅이 자동으로 종료돼요.",
        "지원을 취소했어요. 채팅이 자동으로 종료돼요.",
    ),
    SystemChatEvent.RUNNER_COMPLETED: (
        "꼬붕이 임무를 완료했어요. 행님도 임무 완료를 확인해 주세요.",
        "행님의 임무 완료 확인을 기다리고 있어요.",
    ),
    SystemChatEvent.ORDERER_CONFIRMED: (
        "꼬붕의 임무 완료를 기다리고 있어요.",
        "행님이 임무 완료를 확인했어요. 꼬붕도 임무를 완료해 주세요.",
    ),
    SystemChatEvent.ALL_CONFIRMED: (_FINISHED, _FINISHED),
    SystemChatEvent.DISPUTE_RAISED: (
        "분쟁 중인 임무예요. 분쟁이 해결될 때까지 잠시만 기다려 주세요.",
        "분쟁 중인 임무예요. 분쟁이 해결될 때까지 잠시만 기다려 주세요.",
    ),
    SystemChatEvent.DISPUTE_COMPLETED: (_FINISHED, _FINISHED),
    SystemChatEvent.DISPUTE_FAILED: (_ENDED, _ENDED),
    SystemChatEvent.PROPOSAL_CANCELLED: ("요청이 취소되어 채팅이 종료됐어요.", "요청이 취소되어 채팅이 종료됐어요."),
    SystemChatEvent.ADMIN_CANCELLED_AFTER_MATCH: (_ENDED, _ENDED),
    SystemChatEvent.PAYOUT_COMPLETED: (
        "꼬붕에게 수행비 {amount:,}원이 입금됐어요.",
        "꼬붕에게 수행비 {amount:,}원이 입금됐어요.",
    ),
    SystemChatEvent.REFUND_COMPLETED: ("행님에게 환불이 완료됐어요.", "행님에게 환불이 완료됐어요."),
}


def render_system_chat(event: SystemChatEvent, payload: dict[str, Any] | None, viewer: ChatRole) -> str:
    orderer_text, runner_text = _TEXTS[event]
    text = orderer_text if viewer == ChatRole.ORDERER else runner_text
    return text.format(**(payload or {}))
