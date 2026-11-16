"""관리자 운영 알림 리스너 — 미션 상태 전이 이벤트를 Slack 메시지로 조립한다.

여기서는 메시지를 만들어 outbox에 쌓기만 한다. 발송은 커밋 이후 BackgroundTask가 한다.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.events.base import EventBus
from app.events.mission_events import MissionCompletedEvent, MissionDisputedEvent
from app.services.admin_alert_outbox import track_admin_alert
from app.services.admin_alert_service import AdminAlert
from app.services.admin.admin_user_display import admin_user_names


def _fee(amount: int) -> str:
    return f"{amount:,}원"


def _names(db: Session, event: MissionDisputedEvent | MissionCompletedEvent) -> tuple[str, str]:
    """행님·꼬붕 이름을 한 번에 읽는다. 탈퇴한 사용자도 표시 문자열로 채워진다."""
    names = admin_user_names(db, [event.orderer_id, event.runner_id])
    return names[event.orderer_id], names[event.runner_id]


def _subject(event: MissionDisputedEvent | MissionCompletedEvent) -> str:
    return f"임무 #{event.mission_id} · 요청 #{event.proposal_id} «{event.proposal_title}»"


def on_mission_disputed(event: MissionDisputedEvent, db: Session) -> None:
    orderer_name, runner_name = _names(db, event)
    track_admin_alert(db, AdminAlert(
        headline="🚨 분쟁이 접수됐어요 — 판정이 필요합니다",
        lines=[
            _subject(event),
            f"행님 {orderer_name} / 꼬붕 {runner_name} · 수행비 {_fee(event.errand_fee)}",
            "관리자 웹에서 완료 또는 실패로 판정해주세요.",
        ],
        link_label="분쟁 처리하러 가기",
        link_path=f"missions/{event.mission_id}",
    ))


def on_mission_completed(event: MissionCompletedEvent, db: Session) -> None:
    _, runner_name = _names(db, event)
    track_admin_alert(db, AdminAlert(
        headline="💰 임무가 완료됐어요 — 수행비 입금이 필요합니다",
        lines=[
            _subject(event),
            f"꼬붕 {runner_name} · 입금 금액 {_fee(event.errand_fee)}",
            "꼬붕 정산 계좌로 입금한 뒤 관리자 웹에 지급을 기록해주세요.",
        ],
        link_label="지급 처리하러 가기",
        link_path=f"missions/{event.mission_id}",
    ))


def register_all() -> None:
    EventBus.register(MissionDisputedEvent, on_mission_disputed)
    EventBus.register(MissionCompletedEvent, on_mission_completed)
