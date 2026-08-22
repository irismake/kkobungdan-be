"""Phone verification policy values and helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from app.core.config import settings
from app.models.user import PhoneVerificationPurpose


DEMO_VERIFICATION_CODE = "123456"
DEMO_LOGIN_PHONE = "01000000000"
VERIFICATION_CODE_TTL_MINUTES = 5
VERIFICATION_CODE_TTL = timedelta(minutes=VERIFICATION_CODE_TTL_MINUTES)
VERIFICATION_CODE_MAX_ATTEMPTS = 5
VERIFICATION_SEND_MAX_COUNT = 3
VERIFICATION_SEND_WINDOW = VERIFICATION_CODE_TTL


def generate_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_verification_code(code: str) -> str:
    return hashlib.sha256(f"{settings.secret_key}:{code}".encode("utf-8")).hexdigest()


def build_verification_message(code: str) -> str:
    return (
        f"[OrderRun] 인증번호는 {code} 입니다. "
        f"{VERIFICATION_CODE_TTL_MINUTES}분 내 입력해 주세요."
    )


def demo_verification_code(
    purpose: PhoneVerificationPurpose,
    phone: str,
) -> str | None:
    is_demo_login = purpose == PhoneVerificationPurpose.LOGIN and phone == DEMO_LOGIN_PHONE
    return DEMO_VERIFICATION_CODE if is_demo_login else None


def is_demo_login_phone(phone: str) -> bool:
    return phone == DEMO_LOGIN_PHONE
