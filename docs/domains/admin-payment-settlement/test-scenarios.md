# Admin/Payment/Settlement Test Scenarios

기준 테스트 파일: `tests/test_admin_integration.py`, `tests/test_admin_web_api_integration.py`,
`tests/test_mission_integration.py`, `tests/test_refund_lifecycle.py`, `tests/test_admin_auth_integration.py`,
`tests/test_dispute_survey_integration.py`, `tests/test_dispute_evidence_integration.py`

## 입금 확인과 자동 취소 (`test_admin_integration.py`)

- 결제 확인은 request body 없이 `HOLDING` Proposal을 공개 상태로 전환하고 오픈채팅방 링크를 저장한다.
- 결제 확인은 `HOLDING`이 아닌 Proposal과 형식이 잘못된 오픈채팅방 링크를 거부한다.
- 결제 확인은 행님에게 알림을 생성한다.
- 입금 확인 대기 Proposal은 생성 후 24시간이 지나면 스케줄러에 의해 `CANCELLED`로 전환된다.
- 미입금 자동 취소 시 행님에게 `PROPOSAL_CANCELLED` 알림이 생성되고, 알림 비활성 사용자는 `SKIPPED`로 저장된다.

## 관리자 웹 처리 (`test_admin_web_api_integration.py`)

- 요청 취소는 연결된 지원과 미션을 함께 종결하고, 이미 취소된 요청은 거부한다.
- 입금 확인된 매칭 전 요청을 취소하면 `ADMIN_CANCELLED` 환불이 생성된다.
- 분쟁 판정이 `COMPLETED`면 미션은 `COMPLETED`, 요청·지원은 `ALL_COMPLETED`가 된다.
- 분쟁 판정이 `FAILED`면 미션은 `FAILED`가 되고 환불이 생성된다.
- 이미 검토된 분쟁의 재판정은 거부한다.
- 입금 확인 전 취소는 `REVIEW` 환불을 남기고, 입금 확인은 이를 `PENDING`으로 올리며 요청을
  `REFUND_PENDING`으로 되돌린다. 입금 없음 종결은 `VOIDED`로 닫고 요청을 `CANCELLED`로 둔다.
- `REVIEW` 환불의 완료 처리와 종결된 환불의 대조 처리는 거부한다.
- 환불 목록은 대기 환불을 Proposal 상태와 함께 반환하고, 상세는 마스킹하지 않은 계좌를 노출한다.
- 환불 완료 기록은 Refund를 `COMPLETED`로, Proposal을 `REFUNDED`로 전이한다.
- 수행비 지급 목록은 `COMPLETED` 미션만 반환하고, 지급 기록은 미션을 `PAID`로 전이한다.
- 수행비 지급 반려는 미션 상태를 `COMPLETED`로 유지한다.
- 관리자 요약은 도메인별 미처리 건수를 집계한다.

## 미션 상태 파생 (`test_mission_integration.py`)

- 지원 수락은 미션을 `STARTED`로 생성하고, 앱 응답에는 미션을 노출하지 않는다.
- 양측 완료 확인은 미션을 `COMPLETED`로, 어느 쪽의 분쟁 접수든 미션을 `DISPUTED`로 전이한다.
- `DISPUTED`가 아닌 미션의 판정과 종료 상태 미션의 재판정은 거부한다.
- `COMPLETED`가 아닌 미션의 지급 기록과 중복 지급은 거부한다.
- 미션 목록은 상태로 필터링되며, 응답에 양측 확인 시각·참여자 이름·오픈채팅방 링크를 담는다.
- 레거시 Offer 분쟁 해결 엔드포인트는 제거되어 존재하지 않는다.

## 환불 수명주기 (`test_refund_lifecycle.py`)

- 제거된 `RESOLVED`, Mission `REFUNDED`, 분쟁 반려 상태는 계약에 남아 있지 않다.
- 환불 상태는 `REVIEW`, `PENDING`, `COMPLETED`, `VOIDED` 네 값이다.
- 완료 판정은 요청·지원을 `ALL_COMPLETED`로, 실패 판정은 요청을 `REFUND_PENDING`, 지원을 `CANCELLED`로 전이한다.
- 환불 완료는 요청을 `REFUNDED`로 전이하고, 이미 처리된 환불의 재처리는 거부한다.
- 매칭 전 취소는 `HOLDING`이면 `CANCELLED`, 입금 확인 후면 `REFUND_PENDING`으로 갈린다.
  `HOLDING` 취소는 환불을 만들지 않는 것이 아니라 `REVIEW` 환불을 남긴다.

## 시나리오 목록

시나리오 ID는 테스트의 `@pytest.mark.scenario("ADMIN-TS-NNN")`와 1:1로 연결된다 ([`tdd-workflow.md`](../../design-docs/tdd-workflow.md)).

| ID | 보장 내용 | 테스트 |
|----|-----------|--------|
| ADMIN-TS-001 | 입금 확인은 `HOLDING` 요청을 공개하고 오픈채팅방 링크를 저장한다 | `test_admin_integration.py::test_confirm_payment_posts_holding_proposal_and_stores_open_chat_url` |
| ADMIN-TS-002 | 입금 확인은 잘못된 오픈채팅방 링크를 거부한다 | `test_admin_integration.py::test_confirm_payment_rejects_invalid_open_chat_url` |
| ADMIN-TS-003 | 입금 확인 시 행님에게 알림이 생긴다 | `test_admin_integration.py::test_confirm_payment_notifies_orderer` |
| ADMIN-TS-004 | 입금 독촉은 입금 대기 요청에 한 번만 보낸다 | `test_admin_integration.py::test_send_payment_reminders_targets_only_pending_payments_once` |
| ADMIN-TS-005 | 알림이 꺼진 행님에게는 입금 독촉을 보내지 않는다 | `test_admin_integration.py::test_send_payment_reminders_skips_notification_when_alarm_disabled` |
| ADMIN-TS-006 | `HOLDING`이 아닌 요청은 입금 확인을 거부한다 | `test_admin_integration.py::test_confirm_payment_rejects_non_holding_proposal` |
| ADMIN-TS-007 | 미입금 자동 취소는 24시간이 지난 `HOLDING` 요청만 취소한다 | `test_admin_integration.py::test_cancel_expired_payment_proposals_only_cancels_holding_after_24_hours` |
| ADMIN-TS-008 | 미입금 자동 취소 시 행님에게 알림이 생긴다 | `test_admin_integration.py::test_cancel_expired_payment_proposals_notifies_orderer` |
| ADMIN-TS-009 | 알림이 꺼진 행님의 자동 취소 알림은 `SKIPPED`로 저장된다 | `test_admin_integration.py::test_cancel_expired_payment_proposals_skips_notification_when_alarm_disabled` |
| ADMIN-TS-010 | 만료된 요청이 없으면 알림을 만들지 않는다 | `test_admin_integration.py::test_cancel_expired_payment_proposals_creates_no_notification_when_nothing_expired` |
| ADMIN-TS-011 | 입금 확인 스케줄러는 세션을 닫고 취소한 수를 반환한다 | `test_admin_integration.py::test_payment_checker_closes_session_and_returns_cancelled_count` |
| ADMIN-TS-012 | 관리자는 입금 대기 요청 목록을 조회한다 | `test_admin_integration.py::test_list_pending_payment_proposals_without_auth` |
| ADMIN-TS-013 | 관리자 요청 목록은 상태로 필터링하고 지원 수를 센다 | `test_admin_web_api_integration.py::test_list_proposals_filters_by_status_and_counts_offers` |
| ADMIN-TS-014 | 관리자 요청 목록 검색어는 요청 ID와 행님 이름에 맞춘다 | `test_admin_web_api_integration.py::test_list_proposals_keyword_matches_id_and_orderer_name` |
| ADMIN-TS-015 | 관리자 요청 상세는 수락된 지원과 임무를 보여준다 | `test_admin_web_api_integration.py::test_get_proposal_detail_exposes_accepted_offer_and_mission` |
| ADMIN-TS-016 | 없는 요청의 관리자 상세는 404다 | `test_admin_web_api_integration.py::test_get_proposal_detail_returns_not_found` |
| ADMIN-TS-017 | 관리자 요청 취소는 지원과 임무까지 함께 종결한다 | `test_admin_web_api_integration.py::test_cancel_proposal_cascades_offer_and_mission` |
| ADMIN-TS-018 | 이미 취소된 요청은 관리자 취소를 거부한다 | `test_admin_web_api_integration.py::test_cancel_proposal_rejects_already_cancelled` |
| ADMIN-TS-019 | 입금된 매칭 전 요청을 관리자가 취소하면 환불이 생긴다 | `test_admin_web_api_integration.py::test_cancel_paid_pre_match_proposal_creates_admin_refund` |
| ADMIN-TS-020 | 입금 대기 목록은 `HOLDING` 요청을 페이지로 반환한다 | `test_admin_web_api_integration.py::test_pending_payment_returns_page_of_holding_proposals` |
| ADMIN-TS-021 | 관리자 지원 목록은 금액·수락·분쟁 여부를 보여준다 | `test_admin_web_api_integration.py::test_list_offers_reports_amount_accepted_and_dispute_flags` |
| ADMIN-TS-022 | 관리자 지원 목록은 요청에 저장된 오픈채팅방 링크를 내려준다 | `test_admin_web_api_integration.py::test_list_offers_returns_proposal_open_chat_url` |
| ADMIN-TS-023 | 관리자 지원 목록은 분쟁 없음으로 필터링할 수 있다 | `test_admin_web_api_integration.py::test_list_offers_filters_by_dispute_absence` |
| ADMIN-TS-024 | 취소된 임무의 지원도 수락 필터에 남는다 | `test_admin_web_api_integration.py::test_list_offers_keeps_cancelled_mission_offer_in_accepted_filter` |
| ADMIN-TS-025 | 분쟁 목록·상세는 접수자와 대상의 역할을 구분한다 | `test_admin_web_api_integration.py::test_list_and_get_dispute_resolves_requester_and_target_roles` |
| ADMIN-TS-026 | 분쟁을 완료로 판정하면 임무를 완료하고 요청을 종결한다 | `test_admin_web_api_integration.py::test_resolve_dispute_completes_mission_and_closes_proposal` |
| ADMIN-TS-027 | 분쟁을 실패로 판정하면 임무가 `FAILED`가 된다 | `test_admin_web_api_integration.py::test_resolve_dispute_with_failed_outcome_marks_mission_failed` |
| ADMIN-TS-028 | 이미 판정한 분쟁은 다시 판정할 수 없다 | `test_admin_web_api_integration.py::test_resolve_dispute_rejects_already_reviewed` |
| ADMIN-TS-029 | 환불 목록은 대기 환불을 요청 상태와 함께 반환한다 | `test_admin_web_api_integration.py::test_list_refunds_returns_pending_refunds_with_proposal_status` |
| ADMIN-TS-030 | 환불 목록은 요청 ID로 필터링한다 | `test_admin_web_api_integration.py::test_list_refunds_filters_by_proposal_id` |
| ADMIN-TS-031 | 관리자 환불 상세는 가리지 않은 계좌번호를 보여준다 | `test_admin_web_api_integration.py::test_get_refund_detail_exposes_unmasked_account` |
| ADMIN-TS-032 | 환불 완료는 기록을 남기고 요청을 종결한다 | `test_admin_web_api_integration.py::test_complete_refund_records_and_cancels_proposal` |
| ADMIN-TS-033 | 미입금 요청 취소는 입금 확인용 `REVIEW` 환불을 남긴다 | `test_admin_web_api_integration.py::test_cancel_unpaid_proposal_leaves_a_deposit_review_refund` |
| ADMIN-TS-034 | 입금이 확인되면 `REVIEW` 환불을 `PENDING`으로 올리고 요청을 `REFUND_PENDING`으로 바꾼다 | `test_admin_web_api_integration.py::test_confirm_deposit_promotes_review_refund_and_reopens_refund_pending` |
| ADMIN-TS-035 | 환불 무효 처리는 취소된 요청을 건드리지 않고 검토를 닫는다 | `test_admin_web_api_integration.py::test_void_refund_closes_review_without_touching_the_cancelled_proposal` |
| ADMIN-TS-036 | 환불 무효 처리는 관리자 메모가 필수다 | `test_admin_web_api_integration.py::test_void_refund_requires_an_admin_note` |
| ADMIN-TS-037 | `REVIEW` 환불은 입금 확인을 건너뛸 수 없다 | `test_admin_web_api_integration.py::test_review_refund_cannot_skip_deposit_confirmation` |
| ADMIN-TS-038 | 처리된 환불은 입금 검토 동작을 거부한다 | `test_admin_web_api_integration.py::test_settled_refund_rejects_deposit_review_actions` |
| ADMIN-TS-039 | 지급 목록은 완료된 임무를 반환한다 | `test_admin_web_api_integration.py::test_list_payouts_returns_completed_missions` |
| ADMIN-TS-040 | 지급 완료는 정산 기록을 남긴다 | `test_admin_web_api_integration.py::test_complete_payout_records_settlement` |
| ADMIN-TS-041 | 지급 반려는 임무 상태를 유지한다 | `test_admin_web_api_integration.py::test_reject_payout_keeps_mission_status` |
| ADMIN-TS-042 | 없는 지급 대상은 404다 | `test_admin_web_api_integration.py::test_payout_not_found` |
| ADMIN-TS-043 | 관리자 요약은 영역별 처리 대기 건수를 센다 | `test_admin_web_api_integration.py::test_summary_counts_pending_work_per_domain` |
| ADMIN-TS-044 | 관리자 사용자 목록은 가입 정보를 보여주고 관리자 계정을 뺀다 | `test_admin_web_api_integration.py::test_list_users_returns_signup_profile_and_excludes_admin_accounts` |
| ADMIN-TS-045 | 관리자 사용자 목록 검색어는 이름과 사용자 ID에 맞춘다 | `test_admin_web_api_integration.py::test_list_users_keyword_matches_name_and_user_id` |
| ADMIN-TS-046 | 탈퇴한 사용자는 `"탈퇴한 사용자"`로 보인다 | `test_admin_web_api_integration.py::test_list_users_shows_withdrawn_placeholder_name` |
| ADMIN-TS-047 | 관리자 사용자 목록은 페이지와 크기로 페이징한다 | `test_admin_web_api_integration.py::test_list_users_paginates_by_page_and_size` |
| ADMIN-TS-048 | 지원을 수락하면 임무가 시작된다 | `test_mission_integration.py::test_accepting_offer_starts_mission` |
| ADMIN-TS-049 | 지원 수락 응답은 임무를 노출하지 않는다 | `test_mission_integration.py::test_accept_response_does_not_expose_mission` |
| ADMIN-TS-050 | 양측 임무 완료 시 임무가 `COMPLETED`가 된다 | `test_mission_integration.py::test_both_side_confirmation_completes_mission` |
| ADMIN-TS-051 | 꼬붕 분쟁 접수 시 임무가 `DISPUTED`가 된다 | `test_mission_integration.py::test_runner_dispute_moves_mission_to_disputed` |
| ADMIN-TS-052 | 행님 분쟁 접수 시 임무가 `DISPUTED`가 된다 | `test_mission_integration.py::test_orderer_dispute_moves_mission_to_disputed` |
| ADMIN-TS-053 | 관리자가 분쟁을 완료로 판정한다 | `test_mission_integration.py::test_admin_resolves_dispute_as_completed` |
| ADMIN-TS-054 | 관리자가 분쟁을 실패로 판정한다 | `test_mission_integration.py::test_admin_resolves_dispute_as_failed` |
| ADMIN-TS-055 | 분쟁 중이 아닌 임무는 판정할 수 없다 | `test_mission_integration.py::test_resolve_rejects_mission_that_is_not_disputed` |
| ADMIN-TS-056 | 판정 요청은 판정 결과가 필수다 | `test_mission_integration.py::test_resolve_requires_resolution_field` |
| ADMIN-TS-057 | 수행비 지급 기록 시 임무가 `PAID`가 된다 | `test_mission_integration.py::test_settlement_marks_mission_paid` |
| ADMIN-TS-058 | 완료되지 않은 임무는 지급 기록을 거부한다 | `test_mission_integration.py::test_settlement_rejects_mission_that_is_not_completed` |
| ADMIN-TS-059 | 같은 임무의 지급 기록은 두 번 할 수 없다 | `test_mission_integration.py::test_duplicate_settlement_is_rejected` |
| ADMIN-TS-060 | 종결된 임무는 판정할 수 없다 | `test_mission_integration.py::test_terminal_mission_is_not_resolvable` |
| ADMIN-TS-061 | 없는 임무는 404다 | `test_mission_integration.py::test_mission_not_found_returns_404` |
| ADMIN-TS-062 | 임무 상세는 행님·꼬붕의 완료 확인 시각을 보여준다 | `test_mission_integration.py::test_mission_detail_exposes_each_side_confirmation_time` |
| ADMIN-TS-063 | 임무 목록은 완료 확인 시각을 보여준다 | `test_mission_integration.py::test_mission_list_exposes_confirmation_times` |
| ADMIN-TS-064 | 임무 상세는 행님·꼬붕 이름을 보여준다 | `test_mission_integration.py::test_mission_detail_exposes_participant_names` |
| ADMIN-TS-065 | 임무 목록은 행님·꼬붕 이름을 보여준다 | `test_mission_integration.py::test_mission_list_exposes_participant_names` |
| ADMIN-TS-066 | 임무 상세는 요청에 저장된 오픈채팅방 링크를 내려준다 | `test_mission_integration.py::test_mission_detail_exposes_proposal_open_chat_url` |
| ADMIN-TS-067 | 임무 목록은 요청에 저장된 오픈채팅방 링크를 내려준다 | `test_mission_integration.py::test_mission_list_returns_proposal_open_chat_url` |
| ADMIN-TS-068 | 탈퇴한 참여자 이름은 표시용 문구로 보인다 | `test_mission_integration.py::test_mission_name_uses_display_text_for_withdrawn_participant` |
| ADMIN-TS-069 | 임무 상세는 지급·환불 여부를 보여준다 | `test_mission_integration.py::test_mission_detail_exposes_payout_flags` |
| ADMIN-TS-070 | 임무 목록은 상태로 필터링한다 | `test_mission_integration.py::test_mission_list_filters_by_status` |
| ADMIN-TS-071 | 제거된 지원 판정 엔드포인트는 404다 | `test_mission_integration.py::test_offer_resolve_endpoint_is_removed` |
| ADMIN-TS-072 | 제거된 옛 상태값은 상태 enum에 없다 | `test_refund_lifecycle.py::test_removed_legacy_and_rejection_statuses_are_not_in_contract` |
| ADMIN-TS-073 | 완료 판정은 요청과 지원을 `ALL_COMPLETED`로 바꾼다 | `test_refund_lifecycle.py::test_completed_dispute_moves_proposal_and_offer_to_all_completed` |
| ADMIN-TS-074 | 실패 판정은 요청을 환불 대기, 지원을 `CANCELLED`로 바꾼다 | `test_refund_lifecycle.py::test_failed_dispute_moves_proposal_to_refund_and_offer_to_cancelled` |
| ADMIN-TS-075 | 환불 완료 시 요청이 `REFUNDED`가 된다 | `test_refund_lifecycle.py::test_refund_completion_moves_proposal_to_refunded` |
| ADMIN-TS-076 | 매칭 전 취소는 입금 전과 입금 후 요청을 구분해 처리한다 | `test_refund_lifecycle.py::test_pre_match_cancel_distinguishes_unpaid_and_paid_proposals` |
| ADMIN-TS-077 | 처리된 환불은 다시 처리할 수 없다 | `test_refund_lifecycle.py::test_processed_refund_cannot_be_processed_again` |
| ADMIN-TS-078 | 입금 검토를 확인하면 `PENDING` 환불이 된다 | `test_refund_lifecycle.py::test_deposit_review_confirms_into_a_pending_refund` |
| ADMIN-TS-079 | 입금 검토 무효 처리는 취소된 요청을 건드리지 않는다 | `test_refund_lifecycle.py::test_deposit_review_voids_without_touching_the_cancelled_proposal` |
| ADMIN-TS-080 | 입금 확인 전 `REVIEW` 환불은 완료할 수 없다 | `test_refund_lifecycle.py::test_review_refund_cannot_be_completed_before_deposit_is_confirmed` |
| ADMIN-TS-081 | 검토 단계를 지난 환불은 입금 검토 동작을 거부한다 | `test_refund_lifecycle.py::test_deposit_review_actions_reject_refunds_past_the_review_step` |
| ADMIN-TS-082 | 관리자 API는 토큰이 없으면 거부한다 | `test_admin_auth_integration.py::test_admin_paths_reject_missing_token` |
| ADMIN-TS-083 | 관리자 API는 관리자가 아닌 사용자를 거부한다 | `test_admin_auth_integration.py::test_admin_paths_reject_non_admin_user` |
| ADMIN-TS-084 | 관리자 API는 관리자 토큰을 받아들인다 | `test_admin_auth_integration.py::test_admin_paths_accept_admin_token` |
| ADMIN-TS-085 | 관리자 변경 API는 관리자가 아닌 사용자를 거부한다 | `test_admin_auth_integration.py::test_admin_mutation_rejects_non_admin_user` |
| ADMIN-TS-086 | 관리자 로그인은 토큰을 발급한다 | `test_admin_auth_integration.py::test_login_issues_tokens_for_admin` |
| ADMIN-TS-087 | 관리자 로그인은 틀린 비밀번호를 거부한다 | `test_admin_auth_integration.py::test_login_rejects_wrong_password` |
| ADMIN-TS-088 | 없는 관리자 아이디도 같은 오류로 거부한다 | `test_admin_auth_integration.py::test_login_rejects_unknown_username_with_same_error` |
| ADMIN-TS-089 | 관리자 로그인을 여러 번 실패하면 계정이 잠긴다 | `test_admin_auth_integration.py::test_login_locks_account_after_repeated_failures` |
| ADMIN-TS-090 | 실패 횟수가 한도 아래면 로그인할 수 있다 | `test_admin_auth_integration.py::test_login_allows_attempts_below_the_limit` |
| ADMIN-TS-091 | 로그인에 성공하면 실패 횟수가 초기화된다 | `test_admin_auth_integration.py::test_successful_login_resets_failure_count` |
| ADMIN-TS-092 | 잠금 시간이 지나면 잠금이 풀린다 | `test_admin_auth_integration.py::test_lock_expires_after_the_lock_duration` |
| ADMIN-TS-093 | 없는 아이디로 실패해도 관리자 계정은 잠기지 않는다 | `test_admin_auth_integration.py::test_unknown_username_does_not_lock_the_admin` |
| ADMIN-TS-094 | 관리자가 아닌 계정은 관리자 로그인을 거부한다 | `test_admin_auth_integration.py::test_login_rejects_non_admin_account` |
| ADMIN-TS-095 | 관리자 로그인의 refresh token으로 토큰을 갱신할 수 있다 | `test_admin_auth_integration.py::test_refresh_token_from_admin_login_works` |
| ADMIN-TS-096 | 관리자 계정 준비는 한 번만 만들고 비밀번호를 유지한다 | `test_admin_auth_integration.py::test_ensure_admin_account_creates_once_and_keeps_password` |
| ADMIN-TS-097 | 관리자 설정이 없으면 계정을 만들지 않는다 | `test_admin_auth_integration.py::test_ensure_admin_account_skips_when_unconfigured` |
| ADMIN-TS-098 | 초기 비밀번호가 없으면 계정을 만들지 않는다 | `test_admin_auth_integration.py::test_ensure_admin_account_skips_without_initial_password` |
| ADMIN-TS-099 | 행님 분쟁 설문 질문은 활성 질문만 표시 순서대로 반환한다 | `test_dispute_survey_integration.py::test_list_order_dispute_survey_questions_returns_active_questions_in_display_order` |
| ADMIN-TS-100 | 꼬붕 분쟁 설문 질문은 꼬붕 대상 질문만 반환한다 | `test_dispute_survey_integration.py::test_list_runner_dispute_survey_questions_returns_runner_questions_only` |
| ADMIN-TS-101 | 설문 질문이 없으면 빈 목록을 반환한다 | `test_dispute_survey_integration.py::test_list_dispute_survey_questions_returns_empty_list` |
| ADMIN-TS-102 | 설문 질문 조회는 입력값과 인증을 검증한다 | `test_dispute_survey_integration.py::test_list_dispute_survey_questions_validation_and_auth_errors` |
| ADMIN-TS-103 | 분쟁 설문 질문 ORM 모델이 계획의 스펙과 같다 | `test_dispute_survey_integration.py::test_dispute_survey_question_model_spec_matches_plan` |
| ADMIN-TS-104 | 상태 컬럼은 이름 붙인 CHECK 제약조건을 선언한다 | `test_dispute_survey_integration.py::test_enum_column_declares_named_check_constraint` |
| ADMIN-TS-105 | DB가 enum 밖의 값을 거부한다 | `test_dispute_survey_integration.py::test_enum_check_constraint_rejects_value_outside_the_enum` |
| ADMIN-TS-106 | 분쟁 증빙 모델은 설문 질문과 임무를 필수로 참조한다 | `test_dispute_survey_integration.py::test_dispute_evidence_model_requires_survey_question_and_mission` |
| ADMIN-TS-107 | 요청 ID로 분쟁 증빙을 참여자가 조회할 수 있다 | `test_dispute_evidence_integration.py::test_get_dispute_evidence_by_proposal_id_allows_participants` |
| ADMIN-TS-108 | 지원 ID로 분쟁 증빙을 참여자가 조회할 수 있다 | `test_dispute_evidence_integration.py::test_get_dispute_evidence_by_offer_id_allows_participants` |
| ADMIN-TS-109 | 분쟁 증빙 조회는 참여자가 아니거나 잘못된 조건이면 거부한다 | `test_dispute_evidence_integration.py::test_get_dispute_evidence_rejects_non_participant_and_invalid_query` |
| ADMIN-TS-110 | 분쟁 증빙이 없으면 404다 | `test_dispute_evidence_integration.py::test_get_dispute_evidence_returns_not_found` |
