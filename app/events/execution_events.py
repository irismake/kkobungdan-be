from __future__ import annotations

from dataclasses import dataclass

from app.events.base import DomainEvent


@dataclass(frozen=True)
class MeetingConfirmedByRunnerEvent(DomainEvent):
    """꼬붕이 완료 처리했을 때 행님에게 알림."""

    offer_id: int
    proposal_id: int
    runner_id: str
    orderer_id: str
    proposal_title: str
    all_completed: bool


@dataclass(frozen=True)
class MeetingConfirmedByOrdererEvent(DomainEvent):
    """행님이 완료 확인했을 때 꼬붕에게 알림."""

    offer_id: int
    proposal_id: int
    orderer_id: str
    runner_id: str
    proposal_title: str
    all_completed: bool


@dataclass(frozen=True)
class DisputeRaisedByOrdererEvent(DomainEvent):
    """행님이 분쟁을 접수했을 때 꼬붕에게 알림."""

    offer_id: int
    proposal_id: int
    orderer_id: str
    runner_id: str
    proposal_title: str


@dataclass(frozen=True)
class DisputeRaisedByRunnerEvent(DomainEvent):
    """꼬붕이 분쟁을 접수했을 때 행님에게 알림."""

    offer_id: int
    proposal_id: int
    runner_id: str
    orderer_id: str
    proposal_title: str
