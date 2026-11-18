"""요청·지원·임무 행 잠금 (CHAT-REQ-026, docs/design-docs/chat-architecture.md "요청·지원 상태와 함께 바뀌는 처리").

서로 겹치는 상태 변경(매칭과 지원 취소, 매칭과 요청 취소, 양측 완료 확인 등)이 하나로만 확정되도록,
상태를 바꾸는 서비스는 검사하기 전에 이 함수들로 행을 잠그고 다시 읽는다.

- 잠금 순서는 항상 요청(proposals) → 지원(offers) → 임무(missions) → 채팅방(chat_rooms)이다. 순서가 같으면 교착이 없다.
- MySQL 기본 격리 수준(REPEATABLE READ)에서는 같은 트랜잭션의 첫 일반 조회(예: 로그인 사용자 확인) 때 읽기
  기준 시점이 정해진다. 그래서 잠금을 기다린 뒤에도 일반 조회는 옛 값을 본다. 잠그는 조회(`FOR UPDATE`)는
  최신 커밋 값을 읽으므로, 판단에 쓰는 행은 여기서 잠가 읽고 세션 객체도 그 값으로 덮어쓴다(`populate_existing`).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.mission import Mission
from app.models.offer import Offer
from app.models.proposal import Proposal


def lock_proposal(db: Session, proposal_id: int) -> Proposal | None:
    return (
        db.query(Proposal)
        .filter(Proposal.id == proposal_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )


def lock_offer(db: Session, offer_id: int) -> Offer | None:
    return (
        db.query(Offer)
        .filter(Offer.id == offer_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )


def lock_offer_with_proposal(db: Session, offer_id: int) -> tuple[Offer | None, Proposal | None]:
    """지원의 요청을 먼저 잠그고 지원을 잠근다. 지원의 요청 ID는 바뀌지 않으므로 일반 조회로 읽어도 된다."""
    proposal_id = db.query(Offer.proposal_id).filter(Offer.id == offer_id).scalar()
    if proposal_id is None:
        return None, None
    proposal = lock_proposal(db, proposal_id)
    return lock_offer(db, offer_id), proposal


def lock_mission(db: Session, mission_id: int) -> Mission | None:
    return (
        db.query(Mission)
        .filter(Mission.id == mission_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )


def lock_mission_of_offer(db: Session, offer_id: int) -> Mission | None:
    return (
        db.query(Mission)
        .filter(Mission.offer_id == offer_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
