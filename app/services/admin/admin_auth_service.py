"""Admin account bootstrap and login. 관리자 웹 전용 인증이다."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, api_error
from app.core.password import hash_password, verify_password
from app.core.security import (
    access_token_expires_in_ms,
    create_access_token,
    create_refresh_token,
)
from app.core.time import utcnow_naive
from app.models.user import User
from app.schemas.user import AuthTokenResponse


logger = logging.getLogger(__name__)


class AdminAuthService:
    """관리자 계정 보증과 로그인."""

    @staticmethod
    def ensure_admin_account(db: Session) -> User | None:
        """설정된 관리자 계정이 없으면 만든다. 이미 있으면 건드리지 않는다.

        비밀번호는 계정을 처음 만들 때만 환경변수에서 읽는다. 기동할 때마다 덮어쓰면
        운영 중에 바꾼 비밀번호가 배포마다 되돌아간다.
        """
        username = settings.admin_username
        if not username:
            return None

        admin = db.query(User).filter(User.admin_username == username).first()
        if admin is not None:
            if not admin.password_hash:
                logger.warning("관리자 계정 %s에 비밀번호가 없습니다. 로그인할 수 없습니다.", username)
            return admin

        if not settings.admin_initial_password:
            logger.warning(
                "ADMIN_USERNAME은 설정됐지만 ADMIN_INITIAL_PASSWORD가 없어 관리자 계정을 만들지 않았습니다."
            )
            return None

        admin = User(
            name="관리자",
            admin_username=username,
            password_hash=hash_password(settings.admin_initial_password),
            is_admin=True,
            alarm_enabled=False,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        logger.info("관리자 계정 %s를 생성했습니다.", username)
        return admin

    @staticmethod
    def login(db: Session, username: str, password: str) -> AuthTokenResponse:
        """아이디와 비밀번호로 관리자 토큰을 발급한다.

        아이디가 없는 경우와 비밀번호가 틀린 경우를 같은 오류로 응답해 계정 존재 여부를 흘리지 않는다.
        """
        admin = (
            db.query(User)
            .filter(
                User.admin_username == username,
                User.is_admin.is_(True),
                User.deleted.is_(False),
            )
            .first()
        )
        if admin is None or not verify_password(password, admin.password_hash):
            raise api_error(AppError.ADMIN_CREDENTIALS_INVALID)

        admin.update_last_login_at(utcnow_naive())
        db.commit()

        return AuthTokenResponse(
            access_token=create_access_token({"sub": str(admin.id)}),
            refresh_token=create_refresh_token({"sub": str(admin.id)}),
            expires_in=access_token_expires_in_ms(),
            user_id=str(admin.id),
        )


__all__ = ["AdminAuthService"]
