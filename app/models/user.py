"""Account and phone-auth persistence models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timedelta

from sqlalchemy import BigInteger, Boolean, CHAR, Column, Computed, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.time import utcnow_naive
from app.models.enum_type import enum_column


class PhoneVerificationPurpose(str, enum.Enum):
    SIGNUP = "SIGNUP"
    LOGIN = "LOGIN"


class PhoneVerificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"


class User(Base):
    """User account model for phone-auth based access."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    password_hash = Column(String(255), nullable=True)
    name = Column(String(100), nullable=True)
    phone = Column(String(20), unique=True, nullable=True, index=True)
    phone_verified_at = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    alarm_enabled = Column(Boolean, nullable=True, default=True, server_default="1")
    level = Column(Integer, nullable=False, default=0, server_default="0")
    # 관리자 웹 전용 계정 표시. 앱 사용자는 항상 거짓이다.
    is_admin = Column(Boolean, nullable=False, default=False, server_default="0")
    # 관리자 로그인 아이디. 관리자 행에만 값이 있다.
    admin_username = Column(String(50), nullable=True, unique=True)
    # 관리자 로그인 실패 잠금. 관리자 계정이 하나뿐이라 계정 단위로 센다.
    admin_login_failed_count = Column(Integer, nullable=False, default=0, server_default="0")
    admin_locked_until = Column(DateTime(timezone=True), nullable=True)
    deleted = Column(Boolean, nullable=False, default=False, server_default="0")
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive, onupdate=utcnow_naive)

    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("admin_username", name="uk_users_admin_username"),)

    def update_last_login_at(self, current_time: datetime) -> None:
        self.last_login_at = current_time

    def is_admin_login_locked(self, current_time: datetime) -> bool:
        return self.admin_locked_until is not None and self.admin_locked_until > current_time

    def record_admin_login_failure(self, current_time: datetime, max_attempts: int, lock_duration: timedelta) -> None:
        """실패를 한 번 세고, 한계에 도달하면 잠근다."""
        self.admin_login_failed_count = (self.admin_login_failed_count or 0) + 1
        if self.admin_login_failed_count >= max_attempts:
            self.admin_locked_until = current_time + lock_duration

    def reset_admin_login_failures(self) -> None:
        self.admin_login_failed_count = 0
        self.admin_locked_until = None

    def update_alarm_setting(self, alarm_enabled: bool) -> None:
        self.alarm_enabled = alarm_enabled

    def update_name(self, name: str) -> None:
        self.name = name

    def verify_phone(self, phone: str, verified_at: datetime) -> None:
        self.phone = phone
        self.phone_verified_at = verified_at

    def withdraw(self, withdrawn_at: datetime) -> None:
        self.deleted = True
        self.deleted_at = withdrawn_at
        self.password_hash = None
        self.name = None
        self.phone = None
        self.phone_verified_at = None
        self.last_login_at = None
        self.alarm_enabled = None


class AuthPhoneVerification(Base):
    """Phone verification records for signup and login flows."""

    __tablename__ = "auth_phone_verifications"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    purpose = Column(enum_column(PhoneVerificationPurpose, 10, table="auth_phone_verifications", column="purpose"), nullable=False, index=True)
    phone = Column(String(20), nullable=False, index=True)
    name = Column(String(100), nullable=True)
    carrier = Column(String(50), nullable=True)
    code_hash = Column(String(100), nullable=False)
    status = Column(enum_column(PhoneVerificationStatus, 20, table="auth_phone_verifications", column="status"), nullable=False, default=PhoneVerificationStatus.PENDING)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    sent_at = Column(DateTime(timezone=True), nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive, onupdate=utcnow_naive)

    __table_args__ = (
        Index("idx_auth_phone_verifications_purpose_phone_status_expires_at", "purpose", "phone", "status", "expires_at"),
        Index("idx_auth_phone_verifications_purpose_phone_status", "purpose", "phone", "status"),
    )


class UserFCMToken(Base):
    """Single FCM token record per user.

    `fcm_token`은 VARCHAR(4096)이라 그대로 유니크 인덱스를 걸 수 없다(utf8mb4 인덱스 길이
    한도 초과). `fcm_token_hash`는 DB가 SHA2로 자동 계산하는 생성 컬럼으로, 여기에 유니크
    인덱스를 걸어 같은 기기 토큰이 여러 유저에게 동시에 남는 것을 막는다. 애플리케이션
    코드는 이 컬럼을 직접 읽거나 쓰지 않는다.
    """

    __tablename__ = "user_fcm_tokens"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(36), nullable=False, unique=True, index=True)
    fcm_token = Column(String(4096), nullable=False)
    fcm_token_hash = Column(
        CHAR(64),
        Computed("SHA2(fcm_token, 256)", persisted=True),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive, onupdate=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("fcm_token_hash", name="uk_user_fcm_tokens_fcm_token_hash"),
    )


class UserWithdrawalReasonQuestion(Base):
    """Active withdrawal-reason choices displayed to users."""

    __tablename__ = "user_withdrawal_reason_questions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    question_text = Column(String(500), nullable=False)
    display_order = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    requires_detail = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive, onupdate=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("display_order", name="uk_user_withdrawal_reason_questions_display_order"),
        Index("idx_user_withdrawal_reason_questions_lookup", "is_active", "display_order", "id"),
    )


class UserWithdrawal(Base):
    """A user's submitted withdrawal reason."""

    __tablename__ = "user_withdrawals"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(36), nullable=False, index=True)
    reason_question_id = Column(BigInteger, nullable=True)
    detail_reason = Column(String(500), nullable=True)
    withdrawn_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow_naive, onupdate=utcnow_naive)

    __table_args__ = (
        Index("idx_user_withdrawals_reason_question_id", "reason_question_id"),
        Index("idx_user_withdrawals_user_withdrawn_at", "user_id", "withdrawn_at"),
    )


__all__ = [
    "AuthPhoneVerification",
    "PhoneVerificationPurpose",
    "PhoneVerificationStatus",
    "User",
    "UserFCMToken",
    "UserWithdrawal",
    "UserWithdrawalReasonQuestion",
]
