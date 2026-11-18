"""수신자별 시스템 채팅 문구·제목·푸시 정책 (CHAT-REQ-021·030, NOTI-REQ-001).

기존 알림을 대체하는 사건은 기존 제목·본문(공백·이모지 포함)을 유지한다.
"""
from __future__ import annotations

from typing import Any

from app.models.chat import ChatRole, SystemChatEvent


_TEXTS: dict[SystemChatEvent, tuple[str, str]] = {
    SystemChatEvent.OFFER_CREATED: (
        "회원님의 요청에 새로운 꼬붕이 생겼어요. 확인해보세요!",
        "지원이 정상적으로 접수됐어요. 행님의 선택을 기다려주세요.",
    ),
    SystemChatEvent.MATCHED: (
        "꼬붕을 선택하셨어요! 임무를 바로 시작해보세요.",
        "행님이 회원님을 선택했어요.",
    ),
    SystemChatEvent.NOT_SELECTED: (
        "다른 꼬붕과 매칭되어 채팅이 종료됐어요.",
        "이번엔 선택받지 못했지만 다음 기회가 분명 있을 거예요. 다시 도전해보세요!",
    ),
    SystemChatEvent.OFFER_CANCELLED: (
        "꼬붕이 지원을 취소했어요. 채팅이 자동으로 종료돼요.",
        "지원을 취소했어요. 채팅이 자동으로 종료돼요.",
    ),
    SystemChatEvent.RUNNER_COMPLETED: (
        "꼬붕이 임무를 완료했어요. 회원님도 확인해주시면 수행비가 꼬붕에게 전달돼요.",
        "행님의 임무 완료 확인을 기다리고 있어요.",
    ),
    SystemChatEvent.ORDERER_CONFIRMED: (
        "꼬붕의 임무 완료를 기다리고 있어요.",
        "행님이 임무 완료를 확인했어요. 회원님도 앱에서 임무 완료를 눌러주시면 정산이 바로 진행돼요!",
    ),
    SystemChatEvent.ALL_CONFIRMED: (
        "양측 모두 임무 완료를 확인했어요. 성공적으로 임무 수행이 완료됐습니다!",
        "양측 모두 임무 완료를 확인했어요. 성공적으로 임무 수행이 완료됐습니다!",
    ),
    SystemChatEvent.DISPUTE_RAISED: (
        "분쟁 중인 임무예요. 분쟁이 해결될 때까지 잠시만 기다려 주세요.",
        "분쟁 중인 임무예요. 분쟁이 해결될 때까지 잠시만 기다려 주세요.",
    ),
    SystemChatEvent.DISPUTE_COMPLETED: (
        "임무가 완료됐어요. 정산이 곧 시작돼요.",
        "임무가 완료됐어요. 정산이 곧 시작돼요.",
    ),
    SystemChatEvent.DISPUTE_FAILED: (
        "종료된 임무예요. 더 이상 진행할 수 없어요.",
        "종료된 임무예요. 더 이상 진행할 수 없어요.",
    ),
    SystemChatEvent.PROPOSAL_CANCELLED: (
        "요청이 취소되어 채팅이 종료됐어요.",
        "요청이 취소되어 채팅이 종료됐어요.",
    ),
    SystemChatEvent.ADMIN_CANCELLED_AFTER_MATCH: (
        "종료된 임무예요. 더 이상 진행할 수 없어요.",
        "종료된 임무예요. 더 이상 진행할 수 없어요.",
    ),
    SystemChatEvent.PAYOUT_COMPLETED: (
        "꼬붕에게 수행비 {amount:,}원이 입금됐어요.",
        "{amount:,}원이 회원님 계좌로 입금됐어요. 오늘도 멋진 활동 감사해요!",
    ),
    SystemChatEvent.REFUND_COMPLETED: (
        "행님에게 환불이 완료됐어요.",
        "행님에게 환불이 완료됐어요.",
    ),
}

_TITLES: dict[tuple[SystemChatEvent, ChatRole], str] = {
    (SystemChatEvent.OFFER_CREATED, ChatRole.ORDERER): "누군가 지원했어요! 👀",
    (SystemChatEvent.OFFER_CREATED, ChatRole.RUNNER): "지원 완료! ✅",
    (SystemChatEvent.MATCHED, ChatRole.ORDERER): "임무가 시작됐어요! 🏃",
    (SystemChatEvent.MATCHED, ChatRole.RUNNER): "선택받으셨어요! 🙌",
    (SystemChatEvent.NOT_SELECTED, ChatRole.RUNNER): "이번엔 아쉽게 됐어요 😢",
    (SystemChatEvent.RUNNER_COMPLETED, ChatRole.ORDERER): "꼬붕이 임무를 완료했어요! 🤝",
    (SystemChatEvent.ORDERER_CONFIRMED, ChatRole.RUNNER): "행님이 임무 완료를 확인했어요! 🤝",
    (SystemChatEvent.ALL_CONFIRMED, ChatRole.ORDERER): "임무 수행 완료! 수고하셨어요 🎊",
    (SystemChatEvent.ALL_CONFIRMED, ChatRole.RUNNER): "임무 수행 완료! 수고하셨어요 🎊",
    (SystemChatEvent.PAYOUT_COMPLETED, ChatRole.RUNNER): "수행비가 입금됐어요! 💰",
}


def _dispute_recipient(event: SystemChatEvent, payload: dict | None, viewer: ChatRole) -> bool:
    raised_by = (payload or {}).get("raisedBy")
    return event == SystemChatEvent.DISPUTE_RAISED and raised_by in {"ORDERER", "RUNNER"} and viewer.value != raised_by


def render_system_chat(event: SystemChatEvent, payload: dict[str, Any] | None, viewer: ChatRole) -> str:
    if _dispute_recipient(event, payload, viewer):
        return (
            "꼬붕이 분쟁을 접수했어요. 앱에서 내용을 확인해주세요."
            if viewer == ChatRole.ORDERER
            else "행님이 분쟁을 접수했어요. 앱에서 내용을 확인해주세요."
        )
    orderer_text, runner_text = _TEXTS[event]
    text = orderer_text if viewer == ChatRole.ORDERER else runner_text
    return text.format(**(payload or {}))


def render_system_title(event: SystemChatEvent, payload: dict[str, Any] | None, viewer: ChatRole) -> str | None:
    """기존 알림 제목. 별도 제목이 없는 안내는 None(푸시는 상대 이름)이다."""
    if _dispute_recipient(event, payload, viewer):
        return "분쟁이 접수되었어요 🚨"
    return _TITLES.get((event, viewer))


def system_chat_delivery(event: SystemChatEvent, role: ChatRole, payload: dict[str, Any] | None) -> tuple[bool, bool]:
    """(안읽음 포함, 푸시). 미선정 행님만 기록으로 남기고 나머지는 시스템 채팅으로 전달한다."""
    if event == SystemChatEvent.NOT_SELECTED and role == ChatRole.ORDERER:
        return False, False
    return True, True
