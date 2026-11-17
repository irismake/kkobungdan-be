from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core import security
from app.schemas.user import AuthSignupSendRequest
from app.services.user_auth import phone_verification
from app.services.user_auth.phone_verification_service import PhoneVerificationService
from app.services.user_auth.user_auth_service import UserAuthService


@pytest.mark.scenario("AUTH-TS-041")
def test_generate_verification_code_returns_zero_padded_six_digits(monkeypatch):
    monkeypatch.setattr(phone_verification.secrets, "randbelow", lambda _: 42)

    assert phone_verification.generate_verification_code() == "000042"


@pytest.mark.scenario("AUTH-TS-042")
def test_hash_verification_code_is_stable_and_code_specific():
    first_hash = phone_verification.hash_verification_code("123456")

    assert first_hash == phone_verification.hash_verification_code("123456")
    assert first_hash != phone_verification.hash_verification_code("654321")


@pytest.mark.scenario("AUTH-TS-043")
def test_verification_code_ttl_and_message_share_policy():
    assert phone_verification.VERIFICATION_CODE_TTL == timedelta(
        minutes=phone_verification.VERIFICATION_CODE_TTL_MINUTES
    )
    assert (
        f"{phone_verification.VERIFICATION_CODE_TTL_MINUTES}분 내 입력해 주세요."
        in phone_verification.build_verification_message("123456")
    )


@pytest.mark.scenario("AUTH-TS-044")
def test_verification_code_max_attempts_policy():
    assert phone_verification.VERIFICATION_CODE_MAX_ATTEMPTS == 5


@pytest.mark.scenario("AUTH-TS-045")
def test_verification_send_rate_limit_policy():
    assert phone_verification.VERIFICATION_SEND_MAX_COUNT == 3
    assert phone_verification.VERIFICATION_SEND_WINDOW == phone_verification.VERIFICATION_CODE_TTL


@pytest.mark.scenario("AUTH-TS-046")
def test_demo_verification_code_is_allowed_only_for_demo_login():
    assert (
        phone_verification.demo_verification_code(
            phone_verification.PhoneVerificationPurpose.LOGIN,
            phone_verification.DEMO_LOGIN_PHONE,
        )
        == "123456"
    )


@pytest.mark.scenario("AUTH-TS-047")
@pytest.mark.parametrize(
    ("purpose", "phone"),
    [
        (phone_verification.PhoneVerificationPurpose.SIGNUP, phone_verification.DEMO_LOGIN_PHONE),
        (phone_verification.PhoneVerificationPurpose.LOGIN, "01012345678"),
        (phone_verification.PhoneVerificationPurpose.SIGNUP, "01012345678"),
        (phone_verification.PhoneVerificationPurpose.LOGIN, "01000000001"),
        (phone_verification.PhoneVerificationPurpose.SIGNUP, "01000000001"),
    ],
)
def test_demo_verification_code_rejects_other_purpose_or_phone(purpose, phone):
    assert phone_verification.demo_verification_code(purpose, phone) is None


@pytest.mark.scenario("AUTH-TS-048")
@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_demo_login_send_persists_fixed_code_without_calling_sms_sender(monkeypatch, app_env):
    monkeypatch.setattr(phone_verification.settings, "app_env", app_env)
    db = MagicMock()
    background_tasks = MagicMock()
    sms_sender = MagicMock()
    service = PhoneVerificationService(sms_sender=sms_sender)
    service.is_send_rate_limited = MagicMock(return_value=False)
    service.expire_pending = MagicMock()

    response = service.send(
        db,
        phone_verification.PhoneVerificationPurpose.LOGIN,
        phone_verification.DEMO_LOGIN_PHONE,
        background_tasks,
    )

    verification = db.add.call_args.args[0]
    assert verification.code_hash == phone_verification.hash_verification_code("123456")
    assert response.phone == phone_verification.DEMO_LOGIN_PHONE
    background_tasks.add_task.assert_not_called()
    sms_sender.send.assert_not_called()


@pytest.mark.scenario("AUTH-TS-049")
def test_demo_login_phone_rejects_signup_before_sms_service():
    db = MagicMock()
    verification_service = MagicMock()
    payload = AuthSignupSendRequest(
        name="데모 회원가입",
        phone=phone_verification.DEMO_LOGIN_PHONE,
        carrier="SKT",
    )

    with pytest.raises(HTTPException) as exc_info:
        UserAuthService.send_signup_verification(
            db,
            verification_service,
            payload,
            MagicMock(),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "PHONE_ALREADY_EXISTS"
    verification_service.send.assert_not_called()


@pytest.mark.scenario("AUTH-TS-050")
def test_access_token_expiration_is_converted_to_milliseconds(monkeypatch):
    monkeypatch.setattr(security.settings, "jwt_access_token_expire_minutes", 30)

    assert security.access_token_expires_in_ms() == 30 * 60 * 1000
