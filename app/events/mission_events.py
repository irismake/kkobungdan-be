"""미션 상태 전이 이벤트. 관리자 운영 알림의 트리거다."""
from __future__ import annotations

from dataclasses import dataclass

from app.events.base import DomainEvent


@dataclass(frozen=True)
class MissionDisputedEvent(DomainEvent):
    """미션이 분쟁중으로 전이했을 때 관리자에게 판정을 요청한다."""

    mission_id: int
    proposal_id: int
    offer_id: int
    proposal_title: str
    errand_fee: int
    orderer_id: str
    runner_id: str


@dataclass(frozen=True)
class MissionCompletedEvent(DomainEvent):
    """미션이 완료로 전이했을 때 관리자에게 수행비 입금을 요청한다.

    양측 만남 확인으로 자동 전이한 경우와 관리자가 분쟁을 완료로 판정한 경우를 모두 포함한다.
    두 경우 다 이 시점부터 수행비 지급 대기이기 때문이다.
    """

    mission_id: int
    proposal_id: int
    offer_id: int
    proposal_title: str
    errand_fee: int
    orderer_id: str
    runner_id: str
