# User/Auth Test Scenarios

기준 테스트 파일: `tests/test_user_auth_integration.py`, `tests/test_phone_verification.py`, `tests/test_timestamps.py`

## 보장 범위

- 회원가입, 로그인, refresh token 갱신, 로그아웃의 기본 흐름과 회원가입 시 FCM 토큰 저장을 검증한다.
- 일반 회원가입/로그인 인증번호는 보안 난수 기반 6자리 값이고 발송된 값만 확인되는지 검증한다.
- staging과 production의 로그인 데모 `01000000000`만 `123456`을 사용하고 SMS 공급자를 호출하지 않는지 검증한다.
- 로그인 데모 번호의 회원가입 발송 요청도 SMS 없이 거절되는지 검증한다.
- 인증번호 재발송이 이전 코드 유효기간 내에도 허용되고, 마지막 코드만 유효함을 검증한다.
- 인증번호 발송이 5분당 3회로 제한되고, 기간 경과 및 인증 성공 시 다시 허용됨을 검증한다.
- 모든 회원가입 번호와 일반 로그인 번호는 환경과 무관하게 `123456` 고정 우회를 허용하지 않는지 검증한다.
- 존재하지 않는 사용자, pending verification 없음, 코드 불일치 같은 인증 실패를 검증한다.
- 사용자 상세, 알림 설정, 닉네임 변경, FCM 토큰 저장 흐름을 검증한다.
- 회원 탈퇴는 사유 조회, 선택 사유 이력 저장, 기타 상세 사유 필수 검증, 개인정보 hard delete, 탈퇴 사용자 익명 표시, 대기 지원 자동 취소, 미결 활동 차단을 검증한다.
- 자동 취소는 `WAITING` Offer만 대상으로 한다. `HOLDING` Proposal은 입금 여부를 알 수 없어 차단 대상이다.
- 진행 중 활동 차단은 `MATCHED`, `ORDER_COMPLETED`, `DISPUTED` Proposal과 `ACCEPTED`, `RUNNER_COMPLETED`, `DISPUTED` Offer를 대상으로 한다.
- SMS background 발송 실패가 verification 저장을 깨지 않는지 확인한다.
- 사용자/인증 문서 모델과 ORM timestamp 관리 규칙을 검증한다.

## 시나리오 목록

시나리오 ID는 테스트의 `@pytest.mark.scenario("AUTH-TS-NNN")`와 1:1로 연결된다 ([`tdd-workflow.md`](../../design-docs/tdd-workflow.md)).

| ID | 보장 내용 | 테스트 |
|----|-----------|--------|
| AUTH-TS-001 | 회원가입·로그인·토큰 갱신·로그아웃 흐름이 동작한다 | `test_user_auth_integration.py::test_signup_login_refresh_and_logout_flow` |
| AUTH-TS-002 | 로그인 확인 시 다른 사용자에게 등록된 FCM 토큰을 현재 사용자로 옮긴다 | `test_user_auth_integration.py::test_login_confirm_reassigns_fcm_token_registered_to_another_user` |
| AUTH-TS-003 | 회원가입 확인은 FCM 토큰을 받아 저장한다 | `test_user_auth_integration.py::test_signup_confirm_accepts_and_stores_fcm_token` |
| AUTH-TS-004 | 회원가입 확인은 빈 FCM 토큰을 거부한다 | `test_user_auth_integration.py::test_signup_confirm_rejects_blank_fcm_token` |
| AUTH-TS-005 | 데모 로그인은 SMS 없이 고정 인증번호를 쓴다 | `test_user_auth_integration.py::test_demo_login_uses_fixed_code_without_sending_sms` |
| AUTH-TS-006 | 데모 로그인 번호로는 SMS 없이 회원가입이 거부된다 | `test_user_auth_integration.py::test_demo_login_phone_rejects_signup_without_sending_sms` |
| AUTH-TS-007 | 가입하지 않은 번호의 로그인 확인은 사용자 없음 오류다 | `test_user_auth_integration.py::test_login_confirm_returns_user_not_found_when_user_does_not_exist` |
| AUTH-TS-008 | 대기 중인 인증이 없으면 로그인 확인은 찾을 수 없음 오류다 | `test_user_auth_integration.py::test_login_confirm_returns_not_found_when_no_pending_verification` |
| AUTH-TS-009 | 로그인 확인에 틀린 인증번호를 내면 불일치 오류다 | `test_user_auth_integration.py::test_login_confirm_returns_code_mismatch_when_wrong_code_submitted` |
| AUTH-TS-010 | 회원가입 확인에 틀린 인증번호를 내면 불일치 오류다 | `test_user_auth_integration.py::test_signup_confirm_returns_code_mismatch_when_wrong_code_submitted` |
| AUTH-TS-011 | 내 정보 조회, 알림 설정 변경, FCM 토큰 등록이 동작한다 | `test_user_auth_integration.py::test_user_detail_alarm_and_fcm_token_flow` |
| AUTH-TS-012 | 이름 변경은 인증이 필요하고 본인 이름만 바꾼다 | `test_user_auth_integration.py::test_update_user_name_requires_auth_and_updates_only_current_user` |
| AUTH-TS-013 | 이름 변경의 입력값 오류는 거부된다 | `test_user_auth_integration.py::test_update_user_name_validation_errors` |
| AUTH-TS-014 | 회원 탈퇴는 개인정보를 지우고 익명화된 활동 기록은 남긴다 | `test_user_auth_integration.py::test_withdraw_user_hard_deletes_pii_and_keeps_anonymized_activity_history` |
| AUTH-TS-015 | 탈퇴 사유 목록은 활성 사유만 표시 순서대로 반환한다 | `test_user_auth_integration.py::test_list_user_withdrawal_reasons_returns_active_ordered_questions` |
| AUTH-TS-016 | 탈퇴는 사유와 상세 사유를 저장한다 | `test_user_auth_integration.py::test_withdraw_user_stores_reason_and_detail` |
| AUTH-TS-017 | 기타 탈퇴 사유는 상세 사유가 필수다 | `test_user_auth_integration.py::test_withdraw_user_requires_detail_for_other_reason` |
| AUTH-TS-018 | 탈퇴 사유는 필수다 | `test_user_auth_integration.py::test_withdraw_user_requires_reason_question_id` |
| AUTH-TS-019 | 비활성이거나 없는 탈퇴 사유는 거부된다 | `test_user_auth_integration.py::test_withdraw_user_rejects_inactive_or_unknown_reason` |
| AUTH-TS-020 | 탈퇴는 대기 중인 지원만 자동 취소한다 | `test_user_auth_integration.py::test_withdraw_user_auto_cancels_only_waiting_offers` |
| AUTH-TS-021 | 종결되지 않은 요청이 있으면 탈퇴할 수 없다 | `test_user_auth_integration.py::test_withdraw_user_blocks_when_user_has_open_proposal` |
| AUTH-TS-022 | 종결되지 않은 지원이 있으면 탈퇴할 수 없다 | `test_user_auth_integration.py::test_withdraw_user_blocks_when_user_has_open_offer` |
| AUTH-TS-023 | 환불 대기 중이면 탈퇴할 수 없다 | `test_user_auth_integration.py::test_withdraw_user_blocks_while_refund_is_pending` |
| AUTH-TS-024 | 환불이 종결되기 전(`REVIEW` 포함)에는 탈퇴할 수 없다 | `test_user_auth_integration.py::test_withdraw_user_blocks_until_refund_is_terminal` |
| AUTH-TS-025 | 탈퇴가 막히면 `HOLDING` 요청은 취소되지 않는다 | `test_user_auth_integration.py::test_withdraw_user_keeps_holding_proposal_when_blocked` |
| AUTH-TS-026 | 지급이 반려된 임무의 꼬붕은 탈퇴할 수 있다 | `test_user_auth_integration.py::test_withdraw_user_allows_runner_after_payout_is_rejected` |
| AUTH-TS-027 | 실패한 임무의 꼬붕은 탈퇴할 수 있다 | `test_user_auth_integration.py::test_withdraw_user_allows_runner_when_mission_failed` |
| AUTH-TS-028 | 수행비 지급 대기 중이면 탈퇴할 수 없다 | `test_user_auth_integration.py::test_withdraw_user_blocks_while_payout_is_pending` |
| AUTH-TS-029 | 익명화가 실패하면 탈퇴의 모든 변경이 롤백된다 | `test_user_auth_integration.py::test_withdraw_user_rolls_back_all_changes_when_anonymization_fails` |
| AUTH-TS-030 | 인증번호 유효 시간 안에 다시 보내면 이전 인증번호를 대체한다 | `test_user_auth_integration.py::test_signup_verification_resend_is_allowed_within_ttl` |
| AUTH-TS-031 | 회원가입 인증번호 발송은 횟수 제한을 받는다 | `test_user_auth_integration.py::test_signup_verification_send_is_rate_limited` |
| AUTH-TS-032 | 제한 시간 창이 지나면 인증번호를 다시 보낼 수 있다 | `test_user_auth_integration.py::test_verification_send_outside_window_is_allowed` |
| AUTH-TS-033 | 인증에 성공하면 발송 횟수 제한이 초기화된다 | `test_user_auth_integration.py::test_successful_verification_resets_send_rate_limit` |
| AUTH-TS-034 | 인증 요청의 상태 전이 규칙을 지킨다 | `test_user_auth_integration.py::test_verification_state_rules` |
| AUTH-TS-035 | 가입 확인 중 중복 사용자가 되면 인증 처리를 롤백한다 | `test_user_auth_integration.py::test_signup_confirm_rolls_back_verification_when_user_becomes_duplicate` |
| AUTH-TS-036 | 회원가입 인증은 백그라운드 SMS가 실패해도 저장된다 | `test_user_auth_integration.py::test_signup_send_persists_verification_even_if_background_sms_fails` |
| AUTH-TS-037 | 미가입 번호로 로그인 인증을 요청하면 사용자 없음 오류다 | `test_user_auth_integration.py::test_login_send_on_unregistered_phone_returns_user_not_found` |
| AUTH-TS-038 | 로그인 인증은 백그라운드 SMS가 실패해도 저장된다 | `test_user_auth_integration.py::test_login_send_persists_verification_even_if_background_sms_fails` |
| AUTH-TS-039 | SMS 발송기가 없으면 인증을 저장하지 않는다 | `test_user_auth_integration.py::test_verification_send_does_not_persist_when_sms_sender_is_missing` |
| AUTH-TS-040 | 사용자·인증 ORM 모델이 문서의 스펙과 같다 | `test_user_auth_integration.py::test_model_spec_matches_user_auth_docs` |
| AUTH-TS-041 | 인증번호는 0으로 채운 6자리다 | `test_phone_verification.py::test_generate_verification_code_returns_zero_padded_six_digits` |
| AUTH-TS-042 | 인증번호 해시는 같은 입력에 같고 번호마다 다르다 | `test_phone_verification.py::test_hash_verification_code_is_stable_and_code_specific` |
| AUTH-TS-043 | 인증번호 유효 시간과 안내 문구가 같은 정책을 쓴다 | `test_phone_verification.py::test_verification_code_ttl_and_message_share_policy` |
| AUTH-TS-044 | 인증번호 최대 시도 횟수 정책을 지킨다 | `test_phone_verification.py::test_verification_code_max_attempts_policy` |
| AUTH-TS-045 | 인증번호 발송 횟수 제한 정책을 지킨다 | `test_phone_verification.py::test_verification_send_rate_limit_policy` |
| AUTH-TS-046 | 데모 인증번호는 데모 로그인에만 허용된다 | `test_phone_verification.py::test_demo_verification_code_is_allowed_only_for_demo_login` |
| AUTH-TS-047 | 데모 인증번호는 다른 용도나 번호에 거부된다 | `test_phone_verification.py::test_demo_verification_code_rejects_other_purpose_or_phone` |
| AUTH-TS-048 | 데모 로그인 발송은 SMS 없이 고정 인증번호를 저장한다 | `test_phone_verification.py::test_demo_login_send_persists_fixed_code_without_calling_sms_sender` |
| AUTH-TS-049 | 데모 로그인 번호의 회원가입은 SMS 호출 전에 거부된다 | `test_phone_verification.py::test_demo_login_phone_rejects_signup_before_sms_service` |
| AUTH-TS-050 | access token 만료 시간은 밀리초로 변환된다 | `test_phone_verification.py::test_access_token_expiration_is_converted_to_milliseconds` |
| AUTH-TS-051 | 휴대폰 인증 시각은 ORM이 관리한다 | `test_timestamps.py::test_auth_phone_verification_timestamps_are_orm_managed` |
