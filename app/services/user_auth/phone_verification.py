"""Phone verification policy values and helpers."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from app.core.config import settings


LOCAL_TEST_VERIFICATION_CODE = "123456"
LOGIN_TEST_CODE_ALLOWED_ENVS = {"development", "local", "staging"}
VERIFICATION_CODE_TTL_MINUTES = 5
VERIFICATION_CODE_TTL = timedelta(minutes=VERIFICATION_CODE_TTL_MINUTES)
VERIFICATION_CODE_MAX_ATTEMPTS = 5
VERIFICATION_SEND_MAX_COUNT = 3
VERIFICATION_SEND_WINDOW = VERIFICATION_CODE_TTL


def generate_verification_code() -> str:
    return LOCAL_TEST_VERIFICATION_CODE


def hash_verification_code(code: str) -> str:
    return hashlib.sha256(f"{settings.secret_key}:{code}".encode("utf-8")).hexdigest()


def build_verification_message(code: str) -> str:
    return (
        f"[OrderRun] 인증번호는 {code} 입니다. "
        f"{VERIFICATION_CODE_TTL_MINUTES}분 내 입력해 주세요."
    )


def is_login_test_code_allowed(code: str) -> bool:
    return code == LOCAL_TEST_VERIFICATION_CODE and settings.app_env.lower() in LOGIN_TEST_CODE_ALLOWED_ENVS
