"""관리자 응답에서 익명화된 사용자의 표시 이름을 보정한다."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User


WITHDRAWN_USER_NAME = "탈퇴한 사용자"


def admin_user_names(db: Session, user_ids: list[str]) -> dict[str, str]:
    """이름을 일괄 조회하고 탈퇴·누락 사용자는 관리자용 문자열로 표시한다."""
    unique_ids = {user_id for user_id in user_ids if user_id}
    if not unique_ids:
        return {}
    rows = db.query(User.id, User.name).filter(User.id.in_(unique_ids)).all()
    stored_names = {row[0]: row[1] for row in rows}
    return {user_id: stored_names.get(user_id) or WITHDRAWN_USER_NAME for user_id in unique_ids}


__all__ = ["WITHDRAWN_USER_NAME", "admin_user_names"]
