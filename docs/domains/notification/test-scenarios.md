# Notification/SMS Test Scenarios

기준 테스트 파일: `tests/test_notification_integration.py`, `tests/test_sms_service.py`, `tests/test_admin_alert_integration.py`

## 보장 범위

- root 응답의 OpenAPI 예시 shape를 확인한다.
- 알림 목록, 통계, 상세 조회, 읽음 처리를 검증한다.
- 알림 발송 성공과 실패 응답을 검증한다.
- 지원, 수락, 임무 완료, 분쟁 이벤트가 수신자의 `alarm_enabled` 조건에 따라 `PENDING` 또는 `SKIPPED` 알림 레코드를 생성하는지 검증한다.
- 알림 발송 worker는 실제 FCM을 호출하지 않고 fake FCM service의 `send_notification()` 호출 여부, 전달 data, `SENT`/`FAILED` 상태 전이를 검증한다.
- 알림 발송 worker가 `SKIPPED` 알림을 FCM으로 보내거나 상태 변경하지 않는지 검증한다.
- AWS SNS 전화번호 포맷, SMS attributes, provider error 전파를 검증한다.
- 관리자 운영 알림이 임무 `DISPUTED`·`COMPLETED` 전이에서만 발송되고, 한쪽만 임무 완료를 확인한 시점,
  실패 판정, 지급 기록에서는 발송되지 않는지 검증한다.
- 이미 분쟁중인 임무의 상태 동기화가 알림을 중복 생성하지 않는지 검증한다.
- `SlackAdminAlertSender`는 실제 Slack을 호출하지 않고 `httpx.MockTransport`로 payload,
  webhook 미설정 시 no-op, 발송 실패 시 예외 없이 error 로그만 남기는지 검증한다.

## 비보장 범위

- Firebase Admin SDK와 외부 FCM 네트워크 발송은 통합 테스트에서 실행하지 않는다.
- 모바일 OS의 실제 수신, 배지, 사운드, 클릭 동작은 백엔드 테스트 범위가 아니다.
- 실제 Slack Incoming Webhook 엔드포인트로의 네트워크 발송은 실행하지 않는다.

## 시나리오 목록

시나리오 ID는 테스트의 `@pytest.mark.scenario("NOTI-TS-NNN")`와 1:1로 연결된다 ([`tdd-workflow.md`](../../design-docs/tdd-workflow.md)).

| ID | 보장 내용 | 테스트 |
|----|-----------|--------|
| NOTI-TS-001 | 루트 응답이 OpenAPI 예시와 같다 | `test_notification_integration.py::test_root_response_matches_openapi_example` |
| NOTI-TS-002 | 알림 목록·통계·상세 조회와 읽음 처리가 동작한다 | `test_notification_integration.py::test_notification_list_stats_detail_and_mark_read` |
| NOTI-TS-003 | 알림 목록은 필터·페이징을 지원하고 다른 사용자 알림을 섞지 않는다 | `test_notification_integration.py::test_notification_list_filters_pages_and_isolates_users` |
| NOTI-TS-004 | 알림 상세와 읽음 처리는 본인 알림에만 된다 | `test_notification_integration.py::test_notification_detail_and_mark_read_are_user_scoped` |
| NOTI-TS-005 | 알림 발송 API의 성공·없음·잘못된 요청·미인증 경우를 처리한다 | `test_notification_integration.py::test_notification_send_and_failure_cases` |
| NOTI-TS-006 | 알림 워커는 `PENDING` 알림을 FCM 데이터와 함께 보낸다 | `test_notification_integration.py::test_notification_worker_sends_pending_notification_with_fcm_data` |
| NOTI-TS-007 | 알림 워커의 즉시 발송은 지정한 알림만 보낸다 | `test_notification_integration.py::test_notification_worker_flush_pending_limits_to_notification_ids` |
| NOTI-TS-008 | 알림이 꺼진 사용자의 알림은 `SKIPPED`로 저장된다 | `test_notification_integration.py::test_send_to_user_stores_skipped_notification_when_alarm_disabled` |
| NOTI-TS-009 | FCM 발송이 실패하면 알림을 `FAILED`로 표시한다 | `test_notification_integration.py::test_notification_worker_marks_failed_when_fcm_send_fails` |
| NOTI-TS-010 | FCM이 등록 해제된 토큰이라고 하면 토큰을 지운다 | `test_notification_integration.py::test_notification_worker_deletes_stale_token_when_fcm_reports_unregistered` |
| NOTI-TS-011 | FCM 토큰이 없으면 FCM을 부르지 않고 실패 처리한다 | `test_notification_integration.py::test_notification_worker_fails_without_token_and_does_not_call_fcm` |
| NOTI-TS-012 | 알림 워커는 `SKIPPED` 알림을 보내지 않는다 | `test_notification_integration.py::test_notification_worker_ignores_skipped_notifications` |
| NOTI-TS-013 | SMS 발송기는 한국 전화번호를 국제 형식으로 바꾼다 | `test_sms_service.py::test_aws_sns_sms_sender_formats_korean_phone_number` |
| NOTI-TS-014 | SMS 발송기는 SMS 속성을 담아 SNS에 발행한다 | `test_sms_service.py::test_aws_sns_sms_sender_publishes_with_sms_attributes` |
| NOTI-TS-015 | SMS 발송기는 SNS 오류를 그대로 올린다 | `test_sms_service.py::test_aws_sns_sms_sender_propagates_provider_errors` |
| NOTI-TS-016 | 꼬붕 분쟁 접수 시 관리자 Slack 알림이 나간다 | `test_admin_alert_integration.py::test_runner_dispute_alerts_admin` |
| NOTI-TS-017 | 행님 분쟁 접수 시 관리자 Slack 알림이 나간다 | `test_admin_alert_integration.py::test_orderer_dispute_alerts_admin` |
| NOTI-TS-018 | 이미 분쟁 중인 임무는 상태 동기화로 다시 알리지 않는다 | `test_admin_alert_integration.py::test_sync_does_not_realert_for_already_disputed_mission` |
| NOTI-TS-019 | 양측 임무 완료 시 관리자에게 수행비 입금 요청 알림이 나간다 | `test_admin_alert_integration.py::test_both_side_confirmation_alerts_admin_to_pay` |
| NOTI-TS-020 | 관리자가 임무 분쟁을 완료로 판정하면 입금 요청 알림이 나간다 | `test_admin_alert_integration.py::test_admin_mission_resolve_completed_alerts_to_pay` |
| NOTI-TS-021 | 관리자가 임무 분쟁을 실패로 판정하면 알리지 않는다 | `test_admin_alert_integration.py::test_admin_mission_resolve_failed_does_not_alert` |
| NOTI-TS-022 | 분쟁 판정 API로 완료 판정해도 입금 요청 알림이 나간다 | `test_admin_alert_integration.py::test_admin_dispute_resolve_completed_alerts_to_pay` |
| NOTI-TS-023 | 수행비 지급 기록은 알림을 만들지 않는다 | `test_admin_alert_integration.py::test_recording_settlement_does_not_alert` |
| NOTI-TS-024 | webhook URL이 없으면 Slack 발송기는 아무것도 하지 않는다 | `test_admin_alert_integration.py::test_sender_is_noop_without_webhook_url` |
| NOTI-TS-025 | Slack 발송기는 텍스트 payload를 webhook으로 보낸다 | `test_admin_alert_integration.py::test_sender_posts_text_payload_to_webhook` |
| NOTI-TS-026 | Slack 발송 실패는 예외를 올리지 않고 로그만 남긴다 | `test_admin_alert_integration.py::test_sender_swallows_failure_and_logs` |
| NOTI-TS-027 | 관리자 알림 링크는 관리자 웹 주소를 쓴다 | `test_admin_alert_integration.py::test_alert_link_uses_admin_web_base_url` |
| NOTI-TS-028 | 관리자 웹 주소가 없으면 알림에 링크를 넣지 않는다 | `test_admin_alert_integration.py::test_alert_omits_link_when_admin_web_base_url_missing` |
| NOTI-TS-029 | 관리자 알림의 금액은 천 단위로 구분된다 | `test_admin_alert_integration.py::test_fee_is_thousand_separated` |
