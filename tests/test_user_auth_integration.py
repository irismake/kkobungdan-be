from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core.errors import ErrorCode
from app.core.time import utcnow_naive
from app.main import app
from app.models.dispute_evidence import DisputeEvidence
from app.models.mission import MissionStatus
from app.models.notification import Notification
from app.models.offer import Offer, OfferStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.refund import Refund, RefundReason, RefundStatus
from app.models.settlement import SettlementAccount
from app.models.terms import TermsAgreement
from app.models.user import (
    AuthPhoneVerification,
    PhoneVerificationPurpose,
    PhoneVerificationStatus,
    User,
    UserFCMToken,
    UserWithdrawal,
    UserWithdrawalReasonQuestion,
)
from app.schemas.user import UserWithdrawalRequest
from app.services.sms_service import get_sms_sender
from app.services.proposal.proposal_service import ProposalService
from app.services.user_auth.phone_verification import (
    DEMO_LOGIN_PHONE,
    VERIFICATION_CODE_MAX_ATTEMPTS,
    VERIFICATION_SEND_MAX_COUNT,
    VERIFICATION_SEND_WINDOW,
)
from app.services.user_auth.user_withdrawal_service import UserWithdrawalService


WITHDRAWAL_REASONS = (
    ("원하는 임무가 많지 않았어요.", False),
    ("원하는 꼬붕(또는 행님)을 만나기 어려웠어요.", False),
    ("이용 방법이 어려웠어요.", False),
    ("앱이 자주 오류가 났어요.", False),
    ("다른 회원과 문제가 있었어요.", False),
    ("다른 서비스를 이용하려고 해요.", False),
    ("기타", True),
)


def seed_withdrawal_reasons(db) -> list[UserWithdrawalReasonQuestion]:
    reasons = [
        UserWithdrawalReasonQuestion(
            question_text=text,
            display_order=index,
            requires_detail=requires_detail,
            is_active=True,
        )
        for index, (text, requires_detail) in enumerate(WITHDRAWAL_REASONS, start=1)
    ]
    db.add_all(reasons)
    db.commit()
    return reasons


def _extract_code(message: str) -> str:
    match = re.search(r"(\d{6})", message)
    assert match is not None
    return match.group(1)


def _signup(client, sms_sender, name="홍길동", phone="010-1234-5678", carrier="SKT"):
    response = client.post(
        "/v1/auth/signup/send",
        json={"name": name, "phone": phone, "carrier": carrier},
    )
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"success", "data", "message"}
    assert payload["success"] is True
    assert payload["message"] is None
    assert payload["data"]["phone"] == "01012345678"
    assert payload["data"]["expiresAt"] is not None
    code = _extract_code(sms_sender.sent_messages[-1]["message"])
    confirm = client.post(
        "/v1/auth/signup/confirm",
        json={"phone": phone, "code": code},
    )
    assert confirm.status_code == 200
    confirm_payload = confirm.json()
    assert set(confirm_payload) == {"success", "data", "message"}
    assert confirm_payload["message"] is None
    return confirm_payload["data"]


def test_signup_login_refresh_and_logout_flow(client, db, sms_sender):
    signup_data = _signup(client, sms_sender)

    user = db.query(User).filter(User.phone == "01012345678").first()
    assert user is not None
    assert user.name == "홍길동"
    assert user.phone_verified_at is not None
    assert user.last_login_at is not None
    assert user.alarm_enabled is True

    login_send = client.post("/v1/auth/login/send", json={"phone": "010-1234-5678"})
    assert login_send.status_code == 200
    assert login_send.json()["message"] is None
    login_code = _extract_code(sms_sender.sent_messages[-1]["message"])

    login_confirm = client.post(
        "/v1/auth/login/confirm",
        json={"phone": "010-1234-5678", "code": login_code, "fcmToken": "  token-1  "},
    )
    assert login_confirm.status_code == 200
    login_payload = login_confirm.json()
    assert login_payload["message"] is None
    login_data = login_payload["data"]
    assert login_data["userId"] == signup_data["userId"]
    assert login_data["tokenType"] == "Bearer"
    assert login_data["expiresIn"] > 0
    assert login_data["accessToken"]
    assert login_data["refreshToken"]

    fcm = db.query(UserFCMToken).filter(UserFCMToken.user_id == user.id).first()
    assert fcm is not None
    assert fcm.fcm_token == "token-1"

    refresh = client.post(
        "/v1/auth/refresh",
        json={"refreshToken": login_data["refreshToken"]},
    )
    assert refresh.status_code == 200
    refresh_payload = refresh.json()
    assert refresh_payload["message"] is None
    refresh_data = refresh_payload["data"]
    assert refresh_data["accessToken"]
    assert refresh_data["expiresIn"] > 0

    logout = client.post(
        "/v1/auth/logout",
        headers={"Authorization": f"Bearer {login_data['accessToken']}"},
        json={"refreshToken": login_data["refreshToken"]},
    )
    assert logout.status_code == 200
    assert logout.json()["message"] == "로그아웃 되었습니다."
    assert logout.json()["data"] is None
    assert db.query(UserFCMToken).filter(UserFCMToken.user_id == user.id).first() is None


def test_login_confirm_reassigns_fcm_token_registered_to_another_user(client, db, factory, sms_sender):
    holder = factory.user(phone="01012340099", name="이전 로그인 유저")
    db.add(UserFCMToken(user_id=holder.id, fcm_token="shared-device-token"))
    db.commit()

    signup_data = _signup(client, sms_sender)

    login_send = client.post("/v1/auth/login/send", json={"phone": "010-1234-5678"})
    login_code = _extract_code(sms_sender.sent_messages[-1]["message"])
    login_confirm = client.post(
        "/v1/auth/login/confirm",
        json={"phone": "010-1234-5678", "code": login_code, "fcmToken": "shared-device-token"},
    )
    assert login_confirm.status_code == 200

    # 같은 기기 토큰을 새로 로그인한 유저가 가져가고, 이전 유저의 row는 사라진다.
    assert db.query(UserFCMToken).filter(UserFCMToken.user_id == holder.id).first() is None
    new_holder = db.query(UserFCMToken).filter(UserFCMToken.fcm_token == "shared-device-token").one()
    assert new_holder.user_id == signup_data["userId"]


def test_signup_confirm_accepts_and_stores_fcm_token(client, db, sms_sender):
    signup_send = client.post(
        "/v1/auth/signup/send",
        json={"name": "홍길동", "phone": "010-1234-5678", "carrier": "SKT"},
    )
    assert signup_send.status_code == 200
    code = _extract_code(sms_sender.sent_messages[-1]["message"])

    signup_confirm = client.post(
        "/v1/auth/signup/confirm",
        json={"phone": "010-1234-5678", "code": code, "fcmToken": "  signup-token  "},
    )

    assert signup_confirm.status_code == 200
    signup_data = signup_confirm.json()["data"]
    assert signup_data["tokenType"] == "Bearer"
    assert signup_data["accessToken"]
    assert signup_data["refreshToken"]
    user = db.query(User).filter(User.phone == "01012345678").first()
    assert user is not None
    fcm = db.query(UserFCMToken).filter(UserFCMToken.user_id == user.id).first()
    assert fcm is not None
    assert fcm.fcm_token == "signup-token"


def test_signup_confirm_rejects_blank_fcm_token(client, sms_sender):
    signup_send = client.post(
        "/v1/auth/signup/send",
        json={"name": "홍길동", "phone": "010-1234-5678", "carrier": "SKT"},
    )
    assert signup_send.status_code == 200
    code = _extract_code(sms_sender.sent_messages[-1]["message"])

    signup_confirm = client.post(
        "/v1/auth/signup/confirm",
        json={"phone": "010-1234-5678", "code": code, "fcmToken": "   "},
    )

    assert signup_confirm.status_code == 400
    assert signup_confirm.json()["error"]["code"] == "VALIDATION_ERROR"


def test_demo_login_uses_fixed_code_without_sending_sms(client, db, sms_sender):
    # given: 로그인 데모 사용자가 아직 없는 DB
    assert db.query(User).filter(User.phone == DEMO_LOGIN_PHONE).first() is None
    sent_count = len(sms_sender.sent_messages)

    # when: 데모 번호로 발송 후 고정 코드를 확인
    send = client.post("/v1/auth/login/send", json={"phone": DEMO_LOGIN_PHONE})
    assert send.status_code == 200
    response = client.post(
        "/v1/auth/login/confirm",
        json={"phone": DEMO_LOGIN_PHONE, "code": "123456"},
    )

    # then: 로그인 계정이 복구되고 SMS 없이 로그인 성공
    assert response.status_code == 200
    assert response.json()["data"]["accessToken"]
    assert len(sms_sender.sent_messages) == sent_count
    user = db.query(User).filter(User.phone == DEMO_LOGIN_PHONE).first()
    assert user is not None
    assert user.name == "오더런 데모"


def test_demo_login_phone_rejects_signup_without_sending_sms(client, sms_sender):
    sent_count = len(sms_sender.sent_messages)

    response = client.post(
        "/v1/auth/signup/send",
        json={"name": "데모 회원가입", "phone": DEMO_LOGIN_PHONE, "carrier": "SKT"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PHONE_ALREADY_EXISTS"
    assert len(sms_sender.sent_messages) == sent_count


def test_login_confirm_returns_user_not_found_when_user_does_not_exist(client):
    # when: 존재하지 않는 일반 번호로 로그인 확인 요청
    response = client.post(
        "/v1/auth/login/confirm",
        json={"phone": "010-9999-8888", "code": "123456"},
    )

    # then: 404 USER_NOT_FOUND
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "USER_NOT_FOUND"


def test_login_confirm_returns_not_found_when_no_pending_verification(client, sms_sender):
    # given: 가입된 일반 유저, 인증 요청 없음
    _signup(client, sms_sender)

    # when: 코드 확인 요청
    response = client.post(
        "/v1/auth/login/confirm",
        json={"phone": "010-1234-5678", "code": "123456"},
    )

    # then: 404 PHONE_VERIFICATION_NOT_FOUND
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PHONE_VERIFICATION_NOT_FOUND"


def test_login_confirm_returns_code_mismatch_when_wrong_code_submitted(client, sms_sender, monkeypatch):
    # given: 가입된 유저와 임의 인증번호
    _signup(client, sms_sender)
    monkeypatch.setattr(
        "app.services.user_auth.phone_verification_service.generate_verification_code",
        lambda: "234567",
    )

    login_send = client.post("/v1/auth/login/send", json={"phone": "010-1234-5678"})
    assert login_send.status_code == 200
    assert _extract_code(sms_sender.sent_messages[-1]["message"]) == "234567"

    # when: 틀린 코드로 로그인 확인 요청
    response = client.post(
        "/v1/auth/login/confirm",
        json={"phone": "010-1234-5678", "code": "654321"},
    )

    # then: 400 PHONE_VERIFICATION_CODE_MISMATCH
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PHONE_VERIFICATION_CODE_MISMATCH"


def test_signup_confirm_returns_code_mismatch_when_wrong_code_submitted(client, sms_sender, monkeypatch):
    # given: 일반 번호의 임의 회원가입 인증번호
    monkeypatch.setattr(
        "app.services.user_auth.phone_verification_service.generate_verification_code",
        lambda: "234567",
    )

    signup_send = client.post(
        "/v1/auth/signup/send",
        json={"name": "홍길동", "phone": "010-5555-6666", "carrier": "SKT"},
    )
    assert signup_send.status_code == 200
    assert _extract_code(sms_sender.sent_messages[-1]["message"]) == "234567"

    # when: 틀린 코드로 회원가입 확인 요청
    response = client.post(
        "/v1/auth/signup/confirm",
        json={"phone": "010-5555-6666", "code": "654321"},
    )

    # then: 400 PHONE_VERIFICATION_CODE_MISMATCH
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PHONE_VERIFICATION_CODE_MISMATCH"


def test_user_detail_alarm_and_fcm_token_flow(client, db, sms_sender):
    _signup(client, sms_sender)
    user = db.query(User).filter(User.phone == "01012345678").first()
    assert user is not None

    from app.core.security import create_access_token

    token = create_access_token({"sub": str(user.id)})

    detail = client.get("/v1/user/detail", headers={"Authorization": f"Bearer {token}"})
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert set(detail_payload) == {"success", "data", "message"}
    assert detail_payload["message"] is None
    data = detail_payload["data"]
    assert data["id"] == user.id
    assert data["name"] == "홍길동"
    assert data["phone"] == "01012345678"
    assert data["alarmEnabled"] is True
    assert data["level"] == 0
    assert data["phoneVerifiedAt"] is not None

    alarm = client.patch(
        "/v1/user/alarm",
        headers={"Authorization": f"Bearer {token}"},
        json={"alarmEnabled": True},
    )
    assert alarm.status_code == 200
    assert alarm.json()["message"] == "알람 설정이 업데이트되었습니다."
    db.refresh(user)
    assert user.alarm_enabled is True

    fcm = client.patch(
        "/v1/user/fcm-token",
        headers={"Authorization": f"Bearer {token}"},
        json={"fcmToken": "   token-2   "},
    )
    assert fcm.status_code == 200
    assert fcm.json()["message"] == "FCM 토큰이 업데이트되었습니다."
    token_row = db.query(UserFCMToken).filter(UserFCMToken.user_id == user.id).first()
    assert token_row is not None
    assert token_row.fcm_token == "token-2"

    second_fcm = client.patch(
        "/v1/user/fcm-token",
        headers={"Authorization": f"Bearer {token}"},
        json={"fcmToken": "token-3"},
    )
    assert second_fcm.status_code == 200
    assert db.query(UserFCMToken).filter(UserFCMToken.user_id == user.id).count() == 1
    db.refresh(token_row)
    assert token_row.fcm_token == "token-3"

    extra_alarm_field = client.patch(
        "/v1/user/alarm",
        headers={"Authorization": f"Bearer {token}"},
        json={"alarmEnabled": True, "unexpected": True},
    )
    assert extra_alarm_field.status_code == 400
    assert extra_alarm_field.json()["error"]["code"] == "VALIDATION_ERROR"

    blank_fcm = client.patch(
        "/v1/user/fcm-token",
        headers={"Authorization": f"Bearer {token}"},
        json={"fcmToken": "   "},
    )
    assert blank_fcm.status_code == 400
    assert blank_fcm.json()["error"]["code"] == "VALIDATION_ERROR"


def test_update_user_name_requires_auth_and_updates_only_current_user(client, db, factory):
    user = factory.user(phone="01012340001", name="기존닉네임")
    other_user = factory.user(phone="01012340002", name="다른사용자")

    unauthenticated = client.patch("/v1/user/name", json={"name": "인증없음"})
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "INVALID_TOKEN"

    response = client.patch(
        "/v1/user/name",
        headers=factory.headers_for(user),
        json={"name": "  새닉네임  "},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "닉네임이 업데이트되었습니다."

    db.refresh(user)
    db.refresh(other_user)
    assert user.name == "새닉네임"
    assert other_user.name == "다른사용자"

    detail = client.get("/v1/user/detail", headers=factory.headers_for(user))
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["message"] is None
    assert detail_payload["data"]["name"] == "새닉네임"
    assert detail_payload["data"]["phoneVerifiedAt"] is None
    assert detail_payload["data"]["lastLoginAt"] is None


def test_update_user_name_validation_errors(client, factory):
    user = factory.user(phone="01012340003", name="기존닉네임")
    headers = factory.headers_for(user)

    blank = client.patch("/v1/user/name", headers=headers, json={"name": "   "})
    assert blank.status_code == 400
    assert blank.json()["error"]["code"] == "VALIDATION_ERROR"

    too_long = client.patch("/v1/user/name", headers=headers, json={"name": "가" * 101})
    assert too_long.status_code == 400
    assert too_long.json()["error"]["code"] == "VALIDATION_ERROR"

    extra_field = client.patch(
        "/v1/user/name",
        headers=headers,
        json={"name": "새닉네임", "unexpected": True},
    )
    assert extra_field.status_code == 400
    assert extra_field.json()["error"]["code"] == "VALIDATION_ERROR"


def test_withdraw_user_hard_deletes_pii_and_keeps_anonymized_activity_history(client, db, factory):
    reason = seed_withdrawal_reasons(db)[0]
    user = factory.user(phone="01012340004", name="탈퇴사용자")
    headers = factory.headers_for(user)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user_id = user.id
    user_phone = user.phone

    proposal = factory.proposal(orderer_id=user_id, status=ProposalStatus.ALL_COMPLETED)
    offer = factory.offer(proposal_id=proposal.id, runner_id=user_id, status=OfferStatus.ALL_COMPLETED)
    mission = factory.mission(proposal, offer, MissionStatus.PAID)
    evidence = DisputeEvidence(
        proposal_id=proposal.id,
        offer_id=offer.id,
        mission_id=mission.id,
        actor_id=user_id,
        survey_question_id=1,
        reason="탈퇴 전 분쟁 사유",
    )
    fcm_token = UserFCMToken(user_id=user_id, fcm_token="withdraw-token")
    settlement = SettlementAccount(
        user_id=user_id,
        bank_name="신한은행",
        account_holder="탈퇴사용자",
        encrypted_account_number="encrypted",
        masked_account_number="********1234",
    )
    terms = TermsAgreement(
        user_id=user_id,
        terms_of_service=True,
        privacy_policy=True,
        payment_refund_policy=True,
        agreed_at=now,
    )
    verification = AuthPhoneVerification(
        purpose=PhoneVerificationPurpose.LOGIN,
        phone=user_phone,
        code_hash="hash",
        status=PhoneVerificationStatus.VERIFIED,
        expires_at=now + timedelta(minutes=5),
        sent_at=now,
        verified_at=now,
        attempt_count=0,
    )
    notification = Notification(
        user_id=user_id,
        notification_type="custom",
        title="탈퇴 전 알림",
        body="탈퇴 전 알림 본문",
        status="sent",
    )
    db.add_all([evidence, fcm_token, settlement, terms, verification, notification])
    db.commit()

    response = client.delete("/v1/user", headers=headers, json={"reasonQuestionId": reason.id})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "회원 탈퇴가 완료되었습니다."
    # 기타가 아닌 사유라 상세 사유만 null이다.
    assert body["data"]["userId"] == user_id
    assert body["data"]["reasonQuestionId"] == reason.id
    assert body["data"]["reasonQuestionText"] == reason.question_text
    assert body["data"]["detailReason"] is None

    withdrawn_user = db.query(User).filter(User.id == user_id).first()
    assert withdrawn_user is not None
    assert withdrawn_user.deleted is True
    assert withdrawn_user.deleted_at is not None
    assert withdrawn_user.name is None
    assert withdrawn_user.phone is None
    assert withdrawn_user.phone_verified_at is None
    assert withdrawn_user.password_hash is None
    assert withdrawn_user.last_login_at is None
    assert withdrawn_user.alarm_enabled is None

    assert db.query(UserFCMToken).filter(UserFCMToken.user_id == user_id).first() is None
    assert db.query(AuthPhoneVerification).filter(AuthPhoneVerification.phone == user_phone).first() is None
    assert db.query(SettlementAccount).filter(SettlementAccount.user_id == user_id).first() is None
    assert db.query(TermsAgreement).filter(TermsAgreement.user_id == user_id).first() is not None
    assert db.query(Notification).filter(Notification.user_id == user_id).first() is None
    assert db.query(Proposal).filter(Proposal.id == proposal.id, Proposal.orderer_id == user_id).first() is not None
    assert db.query(Offer).filter(Offer.id == offer.id, Offer.runner_id == user_id).first() is not None
    assert db.query(DisputeEvidence).filter(
        DisputeEvidence.id == evidence.id,
        DisputeEvidence.actor_id == user_id,
    ).first() is not None

    activity_viewer = factory.user(phone="01012340012", name="조회사용자")
    proposal_detail = ProposalService.get_proposal_detail(db, proposal.id, activity_viewer.id)
    assert proposal_detail.orderer_name == "탈퇴한 사용자"
    assert proposal_detail.offers[0].runner_name == "탈퇴한 사용자"

    detail = client.get("/v1/user/detail", headers=headers)
    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "USER_NOT_FOUND"

    signup_send = client.post(
        "/v1/auth/signup/send",
        json={"name": "재가입사용자", "phone": user_phone, "carrier": "SKT"},
    )
    assert signup_send.status_code == 200
    withdrawal = db.query(UserWithdrawal).filter(UserWithdrawal.user_id == user_id).one()
    assert withdrawal.reason_question_id == reason.id
    assert withdrawal.detail_reason is None
    assert withdrawal.withdrawn_at == withdrawn_user.deleted_at


def test_list_user_withdrawal_reasons_returns_active_ordered_questions(client, db, auth_headers):
    reasons = seed_withdrawal_reasons(db)
    db.add(
        UserWithdrawalReasonQuestion(
            question_text="비활성",
            display_order=8,
            requires_detail=False,
            is_active=False,
        )
    )
    db.commit()

    response = client.get("/v1/user/withdrawal-reasons", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"] == [
        {
            "id": reason.id,
            "questionText": reason.question_text,
            "displayOrder": reason.display_order,
            "requiresDetail": reason.requires_detail,
        }
        for reason in reasons
    ]


def test_withdraw_user_stores_reason_and_detail(client, db, factory):
    reasons = seed_withdrawal_reasons(db)
    reason = reasons[0]
    user = factory.user(phone="01012340104", name="탈퇴사유사용자")
    headers = factory.headers_for(user)

    response = client.delete(
        "/v1/user",
        headers=headers,
        json={"reasonQuestionId": reason.id, "detailReason": " 임무가 부족했습니다. "},
    )

    assert response.status_code == 200
    withdrawal = db.query(UserWithdrawal).filter(UserWithdrawal.user_id == user.id).one()
    assert withdrawal.reason_question_id == reason.id
    assert withdrawal.detail_reason == "임무가 부족했습니다."

    # 신고·분쟁과 같은 사유 3종을 응답한다.
    data = response.json()["data"]
    assert data["reasonQuestionId"] == reason.id
    assert data["reasonQuestionText"] == reason.question_text
    assert data["detailReason"] == "임무가 부족했습니다."
    assert data["userId"] == user.id


def test_withdraw_user_requires_detail_for_other_reason(client, db, factory):
    reasons = seed_withdrawal_reasons(db)
    other_reason = next(reason for reason in reasons if reason.requires_detail)
    user = factory.user(phone="01012340105", name="기타사유사용자")
    headers = factory.headers_for(user)

    response = client.delete("/v1/user", headers=headers, json={"reasonQuestionId": other_reason.id})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"] == "detailReason"
    db.refresh(user)
    assert user.deleted is False
    assert db.query(UserWithdrawal).filter(UserWithdrawal.user_id == user.id).first() is None


def test_withdraw_user_requires_reason_question_id(client, db, factory):
    """탈퇴 사유는 필수다. 신고·분쟁과 같은 정책이다."""
    seed_withdrawal_reasons(db)
    user = factory.user(phone="01012340107", name="사유없는탈퇴사용자")
    headers = factory.headers_for(user)

    no_body = client.delete("/v1/user", headers=headers)
    missing_reason = client.delete("/v1/user", headers=headers, json={"detailReason": "사유는 고르지 않음"})

    assert no_body.status_code == 400
    assert no_body.json()["error"]["code"] == "VALIDATION_ERROR"
    assert missing_reason.status_code == 400
    assert missing_reason.json()["error"]["code"] == "VALIDATION_ERROR"
    db.refresh(user)
    assert user.deleted is False
    assert db.query(UserWithdrawal).filter(UserWithdrawal.user_id == user.id).first() is None


def test_withdraw_user_rejects_inactive_or_unknown_reason(client, db, factory):
    inactive_reason = UserWithdrawalReasonQuestion(
        question_text="비활성",
        display_order=1,
        requires_detail=False,
        is_active=False,
    )
    db.add(inactive_reason)
    db.commit()
    user = factory.user(phone="01012340106", name="비활성사유사용자")
    headers = factory.headers_for(user)

    response = client.delete("/v1/user", headers=headers, json={"reasonQuestionId": inactive_reason.id})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"] == "reasonQuestionId"
    db.refresh(user)
    assert user.deleted is False
    assert db.query(UserWithdrawal).filter(UserWithdrawal.user_id == user.id).first() is None


def test_withdraw_user_auto_cancels_only_waiting_offers(db, factory):
    """돈이 오간 적 없는 대기 지원만 탈퇴와 함께 종결한다."""
    reason = seed_withdrawal_reasons(db)[0]
    user = factory.user(phone="01012340005", name="지원사용자")
    db.add(UserFCMToken(user_id=user.id, fcm_token="kept-token"))
    own_waiting_offer = factory.offer(
        proposal_id=factory.proposal(orderer_id=factory.user(phone="01012340009").id).id,
        runner_id=user.id,
    )
    other_waiting_offer = factory.offer(
        proposal_id=factory.proposal(orderer_id=factory.user(phone="01012340008").id).id,
        runner_id=factory.user(phone="01012340010").id,
    )
    db.commit()

    UserWithdrawalService.withdraw_user(db, user, UserWithdrawalRequest(reasonQuestionId=reason.id))

    db.refresh(own_waiting_offer)
    db.refresh(other_waiting_offer)
    db.refresh(user)
    assert own_waiting_offer.status == OfferStatus.CANCELLED
    assert other_waiting_offer.status == OfferStatus.WAITING
    assert user.deleted is True


@pytest.mark.parametrize(
    ("proposal_status", "expected_code"),
    [
        (ProposalStatus.HOLDING, ErrorCode.USER_WITHDRAWAL_BLOCKED_PROPOSAL_DEPOSIT),
        (ProposalStatus.POSTED, ErrorCode.USER_WITHDRAWAL_BLOCKED_PROPOSAL),
        (ProposalStatus.OFFERED, ErrorCode.USER_WITHDRAWAL_BLOCKED_PROPOSAL),
        (ProposalStatus.MATCHED, ErrorCode.USER_WITHDRAWAL_BLOCKED_PROPOSAL),
        (ProposalStatus.ORDER_COMPLETED, ErrorCode.USER_WITHDRAWAL_BLOCKED_PROPOSAL),
        (ProposalStatus.DISPUTED, ErrorCode.USER_WITHDRAWAL_BLOCKED_PROPOSAL),
        (ProposalStatus.REFUND_PENDING, ErrorCode.USER_WITHDRAWAL_BLOCKED_REFUND),
    ],
)
def test_withdraw_user_blocks_when_user_has_open_proposal(db, factory, proposal_status, expected_code):
    user = factory.user(phone="01012340006", name="오더사용자")
    proposal = factory.proposal(orderer_id=user.id, status=proposal_status)

    with pytest.raises(HTTPException) as exc_info:
        UserWithdrawalService.withdraw_user(db, user)

    assert exc_info.value.status_code == 409
    # 입금 확인 대기는 진행 중인 거래와 코드·문구가 갈린다.
    assert exc_info.value.detail["code"] == expected_code
    db.refresh(user)
    db.refresh(proposal)
    assert user.deleted is False
    assert proposal.status == proposal_status
    assert db.query(UserWithdrawal).filter(UserWithdrawal.user_id == user.id).first() is None


@pytest.mark.parametrize(
    "offer_status",
    [OfferStatus.ACCEPTED, OfferStatus.RUNNER_COMPLETED, OfferStatus.DISPUTED],
)
def test_withdraw_user_blocks_when_user_has_open_offer(db, factory, offer_status):
    user = factory.user(phone="01012340006", name="러너사용자")
    orderer = factory.user(phone="01012340007", name="오더사용자")
    proposal = factory.proposal(orderer_id=orderer.id, status=ProposalStatus.CANCELLED)
    offer = factory.offer(proposal_id=proposal.id, runner_id=user.id, status=offer_status)

    with pytest.raises(HTTPException) as exc_info:
        UserWithdrawalService.withdraw_user(db, user)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == ErrorCode.USER_WITHDRAWAL_BLOCKED_OFFER
    db.refresh(user)
    db.refresh(offer)
    assert user.deleted is False
    assert offer.status == offer_status
    assert db.query(UserWithdrawal).filter(UserWithdrawal.user_id == user.id).first() is None


def test_withdraw_user_blocks_while_refund_is_pending(db, factory):
    orderer = factory.user(phone="01012340017", name="환불대기행님")
    runner = factory.user(phone="01012340018", name="꼬붕")
    proposal, offer = factory.execution(orderer, runner, ProposalStatus.REFUND_PENDING, OfferStatus.CANCELLED)
    mission = factory.mission(proposal, offer, MissionStatus.FAILED)
    factory.refund(proposal, mission)

    with pytest.raises(HTTPException) as exc_info:
        UserWithdrawalService.withdraw_user(db, orderer)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == ErrorCode.USER_WITHDRAWAL_BLOCKED_REFUND


@pytest.mark.parametrize(
    ("refund_status", "blocked"),
    [
        (RefundStatus.REVIEW, True),
        (RefundStatus.PENDING, True),
        (RefundStatus.VOIDED, False),
        (RefundStatus.COMPLETED, False),
    ],
)
def test_withdraw_user_blocks_until_refund_is_terminal(db, factory, refund_status, blocked):
    """REVIEW는 입금 여부를 모르는 단계라 확정된 PENDING과 같이 계좌를 지킨다."""
    reason = seed_withdrawal_reasons(db)[0]
    orderer = factory.user(phone="01012340021", name="취소행님")
    proposal = factory.proposal(orderer_id=orderer.id, status=ProposalStatus.CANCELLED)
    factory.refund(proposal, reason=RefundReason.USER_CANCELLED, status=refund_status)

    if blocked:
        with pytest.raises(HTTPException) as exc_info:
            UserWithdrawalService.withdraw_user(db, orderer, UserWithdrawalRequest(reasonQuestionId=reason.id))
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == ErrorCode.USER_WITHDRAWAL_BLOCKED_REFUND
        db.refresh(orderer)
        assert orderer.deleted is False
    else:
        UserWithdrawalService.withdraw_user(db, orderer, UserWithdrawalRequest(reasonQuestionId=reason.id))
        db.refresh(orderer)
        assert orderer.deleted is True


def test_withdraw_user_keeps_holding_proposal_when_blocked(db, factory):
    """HOLDING은 차단 대상이므로 탈퇴 실패 시 요청이 취소되지 않는다."""
    user = factory.user(phone="01012340022", name="입금대기행님")
    proposal = factory.proposal(orderer_id=user.id, status=ProposalStatus.HOLDING)

    with pytest.raises(HTTPException) as exc_info:
        UserWithdrawalService.withdraw_user(db, user)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == ErrorCode.USER_WITHDRAWAL_BLOCKED_PROPOSAL_DEPOSIT
    db.refresh(proposal)
    assert proposal.status == ProposalStatus.HOLDING
    assert db.query(Refund).filter(Refund.proposal_id == proposal.id).first() is None


def test_withdraw_user_allows_runner_after_payout_is_rejected(db, factory):
    """지급 반려된 COMPLETED 미션은 꼬붕 쪽 의무가 끝난 종결 상태다."""
    reason = seed_withdrawal_reasons(db)[0]
    orderer = factory.user(phone="01012340023", name="행님")
    runner = factory.user(phone="01012340024", name="반려꼬붕")
    proposal, offer = factory.execution(orderer, runner, ProposalStatus.ALL_COMPLETED, OfferStatus.ALL_COMPLETED)
    factory.mission(proposal, offer, MissionStatus.COMPLETED, settlement_rejected_at=utcnow_naive())

    UserWithdrawalService.withdraw_user(db, runner, UserWithdrawalRequest(reasonQuestionId=reason.id))

    db.refresh(runner)
    assert runner.deleted is True


def test_withdraw_user_allows_runner_when_mission_failed(db, factory):
    """FAILED 미션은 수행비 지급 대상이 아니라 지급 시각이 비어 있어도 종결이다."""
    reason = seed_withdrawal_reasons(db)[0]
    orderer = factory.user(phone="01012340025", name="행님")
    runner = factory.user(phone="01012340026", name="분쟁패배꼬붕")
    proposal, offer = factory.execution(orderer, runner, ProposalStatus.REFUNDED, OfferStatus.CANCELLED)
    factory.mission(proposal, offer, MissionStatus.FAILED)

    UserWithdrawalService.withdraw_user(db, runner, UserWithdrawalRequest(reasonQuestionId=reason.id))

    db.refresh(runner)
    assert runner.deleted is True


def test_withdraw_user_blocks_while_payout_is_pending(db, factory):
    orderer = factory.user(phone="01012340019", name="행님")
    runner = factory.user(phone="01012340020", name="지급대기꼬붕")
    proposal, offer = factory.execution(orderer, runner, ProposalStatus.ALL_COMPLETED, OfferStatus.ALL_COMPLETED)
    factory.mission(proposal, offer, MissionStatus.COMPLETED)

    with pytest.raises(HTTPException) as exc_info:
        UserWithdrawalService.withdraw_user(db, runner)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == ErrorCode.USER_WITHDRAWAL_BLOCKED_PAYOUT


def test_withdraw_user_rolls_back_all_changes_when_anonymization_fails(db, factory, monkeypatch):
    reason = seed_withdrawal_reasons(db)[0]
    user = factory.user(phone="01012340015", name="지원사용자")
    db.add(UserFCMToken(user_id=user.id, fcm_token="rollback-token"))
    proposal = factory.proposal(orderer_id=factory.user(phone="01012340016").id, status=ProposalStatus.OFFERED)
    waiting_offer = factory.offer(proposal_id=proposal.id, runner_id=user.id)
    db.commit()

    def fail_withdraw(self, withdrawn_at):
        raise RuntimeError("anonymization failed")

    monkeypatch.setattr(User, "withdraw", fail_withdraw)

    with pytest.raises(RuntimeError, match="anonymization failed"):
        UserWithdrawalService.withdraw_user(db, user, UserWithdrawalRequest(reasonQuestionId=reason.id))

    db.expire_all()
    assert db.query(User).filter(User.id == user.id, User.deleted.is_(False)).one()
    assert db.query(UserFCMToken).filter(UserFCMToken.user_id == user.id).one()
    assert db.query(Proposal).filter(Proposal.id == proposal.id).one().status == ProposalStatus.OFFERED
    assert db.query(Offer).filter(Offer.id == waiting_offer.id).one().status == OfferStatus.WAITING
    assert db.query(UserWithdrawal).filter(UserWithdrawal.user_id == user.id).first() is None


def test_signup_verification_resend_is_allowed_within_ttl(client, db, sms_sender):
    """Resending before the previous code expires is allowed and supersedes it."""
    phone = "010-9999-1111"
    normalized = "01099991111"

    first = client.post(
        "/v1/auth/signup/send",
        json={"name": "홍길동", "phone": phone, "carrier": "KT"},
    )
    assert first.status_code == 200

    resend = client.post(
        "/v1/auth/signup/send",
        json={"name": "홍길동", "phone": phone, "carrier": "KT"},
    )
    assert resend.status_code == 200
    assert len(sms_sender.sent_messages) >= 2

    pending = (
        db.query(AuthPhoneVerification)
        .filter(
            AuthPhoneVerification.phone == normalized,
            AuthPhoneVerification.status == PhoneVerificationStatus.PENDING,
        )
        .all()
    )
    assert len(pending) == 1

    code = _extract_code(sms_sender.sent_messages[-1]["message"])
    confirm = client.post(
        "/v1/auth/signup/confirm",
        json={"phone": phone, "code": code},
    )
    assert confirm.status_code == 200


def test_signup_verification_send_is_rate_limited(client, db):
    phone = "010-3333-4444"
    normalized = "01033334444"

    for _ in range(VERIFICATION_SEND_MAX_COUNT):
        allowed = client.post(
            "/v1/auth/signup/send",
            json={"name": "홍길동", "phone": phone, "carrier": "KT"},
        )
        assert allowed.status_code == 200

    limited = client.post(
        "/v1/auth/signup/send",
        json={"name": "홍길동", "phone": phone, "carrier": "KT"},
    )
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "PHONE_VERIFICATION_SEND_RATE_LIMITED"

    assert (
        db.query(AuthPhoneVerification)
        .filter(AuthPhoneVerification.phone == normalized)
        .count()
        == VERIFICATION_SEND_MAX_COUNT
    )


def test_verification_send_outside_window_is_allowed(client, db):
    phone = "010-5555-6666"
    normalized = "01055556666"

    for _ in range(VERIFICATION_SEND_MAX_COUNT):
        assert (
            client.post(
                "/v1/auth/signup/send",
                json={"name": "홍길동", "phone": phone, "carrier": "KT"},
            ).status_code
            == 200
        )

    stale = datetime.now(timezone.utc).replace(tzinfo=None) - VERIFICATION_SEND_WINDOW - timedelta(minutes=1)
    for verification in db.query(AuthPhoneVerification).filter(
        AuthPhoneVerification.phone == normalized
    ):
        verification.sent_at = stale
    db.commit()

    reopened = client.post(
        "/v1/auth/signup/send",
        json={"name": "홍길동", "phone": phone, "carrier": "KT"},
    )
    assert reopened.status_code == 200


def test_successful_verification_resets_send_rate_limit(client, db, sms_sender):
    phone = "010-1234-5678"
    normalized = "01012345678"

    _signup(client, sms_sender)

    # Signup consumed one send and verified it; the quota restarts from there.
    for _ in range(VERIFICATION_SEND_MAX_COUNT):
        assert (
            client.post("/v1/auth/login/send", json={"phone": phone}).status_code == 200
        )

    limited = client.post("/v1/auth/login/send", json={"phone": phone})
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "PHONE_VERIFICATION_SEND_RATE_LIMITED"

    verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
    latest = (
        db.query(AuthPhoneVerification)
        .filter(
            AuthPhoneVerification.phone == normalized,
            AuthPhoneVerification.purpose == PhoneVerificationPurpose.LOGIN,
        )
        .order_by(AuthPhoneVerification.id.desc())
        .first()
    )
    latest.status = PhoneVerificationStatus.VERIFIED
    latest.verified_at = verified_at
    db.commit()

    assert client.post("/v1/auth/login/send", json={"phone": phone}).status_code == 200


def test_verification_state_rules(client, db, sms_sender):
    first = client.post(
        "/v1/auth/signup/send",
        json={"name": "홍길동", "phone": "010-2222-3333", "carrier": "KT"},
    )
    assert first.status_code == 200
    duplicate = client.post(
        "/v1/auth/signup/send",
        json={"name": "홍길동", "phone": "01022223333", "carrier": "KT"},
    )
    assert duplicate.status_code == 200

    verification = db.query(AuthPhoneVerification).filter(
        AuthPhoneVerification.phone == "01022223333",
        AuthPhoneVerification.purpose == PhoneVerificationPurpose.SIGNUP,
        AuthPhoneVerification.status == PhoneVerificationStatus.PENDING,
    ).first()
    assert verification is not None
    assert verification.status == PhoneVerificationStatus.PENDING
    assert verification.carrier == "KT"

    mismatch = client.post(
        "/v1/auth/signup/confirm",
        json={"phone": "010-2222-3333", "code": "000000"},
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["error"]["code"] == "PHONE_VERIFICATION_CODE_MISMATCH"

    db.refresh(verification)
    assert verification.attempt_count == 1

    verification.attempt_count = VERIFICATION_CODE_MAX_ATTEMPTS - 1
    db.commit()

    mismatch_again = client.post(
        "/v1/auth/signup/confirm",
        json={"phone": "010-2222-3333", "code": "111111"},
    )
    assert mismatch_again.status_code == 400
    db.refresh(verification)
    assert verification.status == PhoneVerificationStatus.EXPIRED

    expired = client.post(
        "/v1/auth/signup/send",
        json={"name": "홍길동", "phone": "010-2222-3333", "carrier": "KT"},
    )
    assert expired.status_code == 200
    code = _extract_code(sms_sender.sent_messages[-1]["message"])
    verification = db.query(AuthPhoneVerification).filter(
        AuthPhoneVerification.phone == "01022223333",
        AuthPhoneVerification.purpose == PhoneVerificationPurpose.SIGNUP,
        AuthPhoneVerification.status == PhoneVerificationStatus.PENDING,
    ).order_by(AuthPhoneVerification.id.desc()).first()
    assert verification is not None
    verification.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    db.commit()

    expired_confirm = client.post(
        "/v1/auth/signup/confirm",
        json={"phone": "010-2222-3333", "code": code},
    )
    assert expired_confirm.status_code == 400
    assert expired_confirm.json()["error"]["code"] == "PHONE_VERIFICATION_EXPIRED"


def test_signup_confirm_rolls_back_verification_when_user_becomes_duplicate(client, db, sms_sender, factory):
    phone = "01044445555"
    response = client.post(
        "/v1/auth/signup/send",
        json={"name": "홍길동", "phone": phone, "carrier": "SKT"},
    )
    assert response.status_code == 200
    code = _extract_code(sms_sender.sent_messages[-1]["message"])
    verification = db.query(AuthPhoneVerification).filter(
        AuthPhoneVerification.phone == phone,
        AuthPhoneVerification.purpose == PhoneVerificationPurpose.SIGNUP,
    ).one()
    factory.user(phone=phone)

    confirm = client.post("/v1/auth/signup/confirm", json={"phone": phone, "code": code})

    assert confirm.status_code == 409
    assert confirm.json()["error"]["code"] == "PHONE_ALREADY_EXISTS"
    db.refresh(verification)
    assert verification.status == PhoneVerificationStatus.PENDING
    assert verification.verified_at is None


def test_signup_send_persists_verification_even_if_background_sms_fails(client, db):
    class FailingSmsSender:
        def send(self, phone: str, message: str) -> None:
            raise RuntimeError("sms failed")

    app.dependency_overrides[get_sms_sender] = lambda: FailingSmsSender()

    response = client.post(
        "/v1/auth/signup/send",
        json={"name": "홍길동", "phone": "010-3333-4444", "carrier": "SKT"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["phone"] == "01033334444"

    verification = db.query(AuthPhoneVerification).filter(
        AuthPhoneVerification.phone == "01033334444",
        AuthPhoneVerification.purpose == PhoneVerificationPurpose.SIGNUP,
    ).first()
    assert verification is not None
    assert verification.status == PhoneVerificationStatus.PENDING


def test_login_send_on_unregistered_phone_returns_user_not_found(client, db):
    """미가입 번호는 인증 실패가 아니라 대상 부재다. 401이면 클라 인터셉터가 세션을 건드린다."""
    response = client.post("/v1/auth/login/send", json={"phone": "010-9999-8888"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "USER_NOT_FOUND"
    assert response.json()["error"]["message"] == "가입되지 않은 휴대폰 번호입니다. 회원가입 후 이용해주세요."
    assert db.query(AuthPhoneVerification).filter(
        AuthPhoneVerification.phone == "01099998888"
    ).count() == 0


def test_login_send_persists_verification_even_if_background_sms_fails(client, db, factory):
    class FailingSmsSender:
        def send(self, phone: str, message: str) -> None:
            raise RuntimeError("sms failed")

    user = factory.user(phone="01033334445")
    app.dependency_overrides[get_sms_sender] = lambda: FailingSmsSender()

    response = client.post("/v1/auth/login/send", json={"phone": user.phone})

    assert response.status_code == 200
    assert response.json()["data"]["phone"] == user.phone

    verification = db.query(AuthPhoneVerification).filter(
        AuthPhoneVerification.phone == user.phone,
        AuthPhoneVerification.purpose == PhoneVerificationPurpose.LOGIN,
    ).first()
    assert verification is not None
    assert verification.status == PhoneVerificationStatus.PENDING


def test_verification_send_does_not_persist_when_sms_sender_is_missing(client, db, factory):
    login_user = factory.user(phone="01033334446")
    app.dependency_overrides[get_sms_sender] = lambda: None

    signup_response = client.post(
        "/v1/auth/signup/send",
        json={"name": "홍길동", "phone": "010-3333-4447", "carrier": "SKT"},
    )
    login_response = client.post("/v1/auth/login/send", json={"phone": login_user.phone})

    assert signup_response.status_code == 500
    assert signup_response.json()["error"]["code"] == "SMS_SENDER_NOT_CONFIGURED"
    assert login_response.status_code == 500
    assert login_response.json()["error"]["code"] == "SMS_SENDER_NOT_CONFIGURED"
    assert db.query(AuthPhoneVerification).filter(
        AuthPhoneVerification.phone.in_(["01033334447", login_user.phone])
    ).count() == 0


def test_model_spec_matches_user_auth_docs():
    assert str(User.__table__.c.id.type).upper() == "VARCHAR(36)"
    assert str(User.__table__.c.phone.type).upper() == "VARCHAR(20)"
    assert User.__table__.c.phone.unique is True
    assert User.__table__.c.deleted.nullable is False
    assert User.__table__.c.deleted_at.nullable is True
    assert User.__table__.c.name.nullable is True
    assert User.__table__.c.alarm_enabled.nullable is True
    assert User.__table__.c.alarm_enabled.default.arg is True
    assert str(User.__table__.c.alarm_enabled.server_default.arg) == "1"

    assert str(AuthPhoneVerification.__table__.c.id.type).upper() == "BIGINT"
    assert str(AuthPhoneVerification.__table__.c.code_hash.type).upper() == "VARCHAR(100)"
    assert AuthPhoneVerification.__table__.c.attempt_count.nullable is False
    assert AuthPhoneVerification.__table__.foreign_keys == set()

    assert str(UserFCMToken.__table__.c.id.type).upper() == "BIGINT"
    assert str(UserFCMToken.__table__.c.user_id.type).upper() == "VARCHAR(36)"
    assert UserFCMToken.__table__.c.user_id.unique is True
    assert UserFCMToken.__table__.foreign_keys == set()
    assert str(UserFCMToken.__table__.c.fcm_token_hash.type).upper() == "CHAR(64)"
    assert {uc.name for uc in UserFCMToken.__table__.constraints if uc.name} == {
        "uk_user_fcm_tokens_fcm_token_hash",
    }
