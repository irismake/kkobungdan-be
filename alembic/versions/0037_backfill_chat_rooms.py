"""Backfill chat rooms for offers created before chat (기존 지원 채팅방 생성).

Revision ID: 0037_backfill_chat_rooms
Revises: 0036_create_outbox_tables
Create Date: 2026-11-18

CHAT-REQ-001·023, docs/product-specs/chat-requirements.md "기존 기능 영향".
채팅방이 없는 지원마다 채팅방을 1개 만든다. 채팅방 상태는 지원·요청·임무 상태로 정하고,
시스템 채팅·첫 인사·과거 대화는 만들지 않는다(저장된 적이 없다).

- 여러 번 실행해도 결과가 같다. 이미 채팅방이 있는 지원은 건너뛰고(LEFT JOIN … IS NULL),
  그 사이 새 지원이 자기 채팅방을 먼저 만들었으면 `uk_chat_rooms_offer_id`에 걸려 그대로 둔다.
- 매칭 전 취소(`CANCELLED`, 임무 없음)는 기존 데이터로 꼬붕 취소와 관리자 취소를 구분할 수 없어 `OFFER_CANCELLED`로 둔다.
- 되돌리기(downgrade)는 하지 않는다. 채팅방이 생긴 뒤에는 새 채팅과 섞여 구분할 수 없다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0037_backfill_chat_rooms"
down_revision = "0036_create_outbox_tables"
branch_labels = None
depends_on = None


BACKFILL_SQL = """
INSERT INTO chat_rooms (
    offer_id, proposal_id, orderer_id, runner_id, status, status_reason,
    last_seq, orderer_last_read_seq, runner_last_read_seq, version, created_at, updated_at
)
SELECT
    o.id,
    o.proposal_id,
    p.orderer_id,
    o.runner_id,
    CASE
        WHEN o.status IN ('WAITING', 'ACCEPTED', 'RUNNER_COMPLETED') THEN 'ACTIVE'
        WHEN o.status = 'DISPUTED' THEN 'INACTIVE'
        ELSE 'CLOSED'
    END,
    CASE
        WHEN o.status IN ('WAITING', 'ACCEPTED', 'RUNNER_COMPLETED') THEN NULL
        WHEN o.status = 'DISPUTED' THEN
            CASE WHEN EXISTS (
                SELECT 1 FROM dispute_evidences e WHERE e.offer_id = o.id AND e.actor_id = p.orderer_id
            ) THEN 'ORDERER_DISPUTED' ELSE 'RUNNER_DISPUTED' END
        WHEN o.status = 'ALL_COMPLETED' THEN
            CASE WHEN m.resolution = 'COMPLETED' THEN 'DISPUTE_COMPLETED' ELSE 'ALL_CONFIRMED' END
        WHEN m.resolution = 'FAILED' THEN 'DISPUTE_FAILED'
        WHEN m.id IS NOT NULL THEN 'ADMIN_CANCELLED'
        WHEN o.status = 'REJECTED' THEN
            CASE
                WHEN p.status IN ('CANCELLED', 'REFUND_PENDING', 'REFUNDED') THEN 'PROPOSAL_CANCELLED'
                WHEN p.status = 'REPORTED' THEN 'ADMIN_CANCELLED'
                ELSE 'NOT_SELECTED'
            END
        ELSE 'OFFER_CANCELLED'
    END,
    0, 0, 0, 0,
    o.created_at,
    UTC_TIMESTAMP()
FROM offers o
JOIN proposals p ON p.id = o.proposal_id
LEFT JOIN missions m ON m.offer_id = o.id
LEFT JOIN chat_rooms r ON r.offer_id = o.id
WHERE r.id IS NULL
ORDER BY o.id
ON DUPLICATE KEY UPDATE offer_id = chat_rooms.offer_id
"""


def backfill_chat_rooms(bind) -> None:
    """채팅방이 없는 지원마다 채팅방을 만든다. 테스트(CHAT-TS-069·099)도 이 함수를 그대로 부른다."""
    bind.execute(sa.text(BACKFILL_SQL))


def upgrade() -> None:
    backfill_chat_rooms(op.get_bind())


def downgrade() -> None:
    pass
