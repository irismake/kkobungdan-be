"""채팅에서 쓰는 차단 여부 조회 (docs/design-docs/chat-architecture.md "차단").

차단은 user-block.md 구현 때 만든다. 그 전까지는 항상 "차단 없음"이다. 채팅 쪽은 이 함수에만 의존한다.
"""

from __future__ import annotations

import enum

from sqlalchemy.orm import Session


class BlockStatus(str, enum.Enum):
    NONE = "NONE"
    BLOCKED_BY_ME = "BLOCKED_BY_ME"
    BLOCKED_BY_PARTNER = "BLOCKED_BY_PARTNER"


def block_status(db: Session, viewer_id: str, partner_id: str) -> BlockStatus:
    return BlockStatus.NONE
