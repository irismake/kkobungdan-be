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


# 기존 알림(notifications)을 이미 받는 사람. 이 사람에게는 시스템 채팅 푸시를 보내지 않는다(중복 방지).
# 분쟁 접수는 접수당한 쪽이 기존 알림을 받으므로 payload의 raisedBy로 따로 정한다.
_EXISTING_NOTIFICATION: dict[SystemChatEvent, frozenset[ChatRole]] = {
    SystemChatEvent.OFFER_CREATED: frozenset({ChatRole.ORDERER, ChatRole.RUNNER}),
    SystemChatEvent.MATCHED: frozenset({ChatRole.ORDERER, ChatRole.RUNNER}),
    SystemChatEvent.NOT_SELECTED: frozenset({ChatRole.RUNNER}),
    SystemChatEvent.RUNNER_COMPLETED: frozenset({ChatRole.ORDERER}),
    SystemChatEvent.ORDERER_CONFIRMED: frozenset({ChatRole.RUNNER}),
    SystemChatEvent.ALL_CONFIRMED: frozenset({ChatRole.ORDERER, ChatRole.RUNNER}),
    SystemChatEvent.PAYOUT_COMPLETED: frozenset({ChatRole.RUNNER}),
}


def system_chat_delivery(event: SystemChatEvent, role: ChatRole, payload: dict[str, Any] | None) -> tuple[bool, bool]:
    """(안읽음에 포함, 푸시) — CHAT-REQ-021 표의 "기존 알림"·"안읽음·푸시" 칸."""
    if event == SystemChatEvent.NOT_SELECTED and role == ChatRole.ORDERER:
        # 행님에게는 안읽음·푸시 없이 기록만 남긴다.
        return False, False
    if event == SystemChatEvent.DISPUTE_RAISED:
        raised_by = (payload or {}).get("raisedBy")
        return True, role.value == raised_by
    return True, role not in _EXISTING_NOTIFICATION.get(event, frozenset())
