# API Contract/OpenAPI Test Scenarios

기준 테스트 파일: `tests/test_openapi.py`, `tests/test_errors.py`

## 보장 범위

- OpenAPI metadata와 문서화된 모든 성공/실패 케이스 예시 shape가 한국어 API 문서 기준과 일치한다.
- validation error와 표준 HTTP exception detail이 error wrapper 계약을 따른다.
- operation별 성공 예시와 표준 error 예시가 존재하며, 같은 status 안의 실패 케이스가 예시 없이 뭉개지지 않는다.
- 인증, 관리자 결제 확인, Offer 수락 등 대표 request/response 계약을 검증한다.
- legacy collection API가 문서화되지 않음을 확인한다.
- 반복 `status` query parameter가 array query로 노출된다.
- API schema가 다른 API DTO를 상속하지 않는 규칙을 확인한다.
- error catalog 필수 필드, details/header 보존, validation catalog message를 검증한다.

## 시나리오 목록

시나리오 ID는 테스트의 `@pytest.mark.scenario("API-TS-NNN")`와 1:1로 연결된다 ([`tdd-workflow.md`](../../design-docs/tdd-workflow.md)).

| ID | 보장 내용 | 테스트 |
|----|-----------|--------|
| API-TS-001 | OpenAPI에 한국어 API 메타데이터가 있다 | `test_openapi.py::test_openapi_contains_korean_api_metadata` |
| API-TS-002 | 알림 설정 API는 PATCH만 문서화한다 | `test_openapi.py::test_user_alarm_openapi_exposes_only_patch` |
| API-TS-003 | 회원가입 인증 발송 예시가 응답 형태와 같다 | `test_openapi.py::test_auth_signup_send_openapi_examples_match_response_shape` |
| API-TS-004 | 입력값 오류 예시는 표준 에러 형태를 쓴다 | `test_openapi.py::test_validation_error_openapi_example_uses_standard_error_wrapper` |
| API-TS-005 | 모든 API에 성공 예시와 표준 에러 예시가 있다 | `test_openapi.py::test_openapi_operations_have_success_examples_and_standard_error_examples` |
| API-TS-006 | 대표 성공 예시가 응답 계약과 같다 | `test_openapi.py::test_representative_success_examples_match_contracts` |
| API-TS-007 | null인 필드도 예시에서 빠지지 않는다 | `test_openapi.py::test_nullable_fields_stay_visible_in_examples` |
| API-TS-008 | 로그인 확인 요청은 필드를 명시적으로 문서화한다 | `test_openapi.py::test_auth_login_confirm_request_exposes_explicit_fields` |
| API-TS-009 | 관리자 입금 확인은 오픈채팅방 링크를 필수로 문서화한다 | `test_openapi.py::test_admin_confirm_payment_requires_open_chat_url` |
| API-TS-010 | 환불 완료는 환불 리소스로만 할 수 있다 | `test_openapi.py::test_refund_is_completed_only_through_refund_resource` |
| API-TS-011 | 관리자 요청 API는 전용 응답 스키마를 쓴다 | `test_openapi.py::test_admin_proposal_contracts_use_dedicated_response_schemas` |
| API-TS-012 | 관리자 응답의 참여자 이름은 필수 문자열이다 | `test_openapi.py::test_admin_participant_names_are_required_non_nullable_strings` |
| API-TS-013 | 관리자 지급 목록은 정산 상태를 담은 임무 응답을 쓴다 | `test_openapi.py::test_admin_payout_list_uses_mission_response_with_settlement_status` |
| API-TS-014 | 요청·지원 생성은 정산 계좌 필수 오류를 문서화한다 | `test_openapi.py::test_proposal_and_offer_creation_document_required_settlement_account` |
| API-TS-015 | 지원 수락은 요청 본문과 금액 응답 필드가 없다 | `test_openapi.py::test_offer_accept_has_no_request_body_or_amount_response_fields` |
| API-TS-016 | 분쟁 요청 스키마의 필수 필드는 사유 질문 ID뿐이다 | `test_openapi.py::test_dispute_requests_require_reason_question_id_only` |
| API-TS-017 | 분쟁 증빙 조회는 둘 중 하나만 쓰는 조회 조건으로 문서화된다 | `test_openapi.py::test_dispute_evidence_lookup_is_documented_with_exclusive_query_params` |
| API-TS-018 | 앱용 임무 목록 API는 문서에 없다 | `test_openapi.py::test_mission_collection_get_is_not_documented` |
| API-TS-019 | 목록의 상태 필터는 반복 가능한 배열 쿼리다 | `test_openapi.py::test_list_status_filters_are_repeatable_array_query_parameters` |
| API-TS-020 | API 스키마는 다른 API의 DTO를 상속하지 않는다 | `test_openapi.py::test_api_schemas_do_not_inherit_from_other_api_dtos` |
| API-TS-021 | 에러 카탈로그의 모든 코드가 OpenAPI에 나온다 | `test_openapi.py::test_every_catalog_error_code_appears_in_openapi` |
| API-TS-022 | 전역 에러 코드는 API 설명에 문서화된다 | `test_openapi.py::test_route_level_errors_are_documented_in_api_description` |
| API-TS-023 | 모든 API에 500 응답이 선언된다 | `test_openapi.py::test_internal_server_error_is_declared_on_every_operation` |
| API-TS-024 | 에러 카탈로그의 모든 항목에 필수 필드가 있다 | `test_errors.py::test_error_catalog_has_required_fields_for_every_error` |
| API-TS-025 | `api_error`는 표준 HTTP 예외 detail을 만든다 | `test_errors.py::test_api_error_builds_standard_http_exception_detail` |
| API-TS-026 | `api_error`는 details와 headers를 유지한다 | `test_errors.py::test_api_error_preserves_details_and_headers` |
| API-TS-027 | 입력값 오류 detail은 카탈로그 문구를 쓴다 | `test_errors.py::test_error_detail_uses_validation_catalog_message` |
| API-TS-028 | 에러 카탈로그의 모든 문구가 한국어다 | `test_errors.py::test_every_catalog_message_is_korean` |
| API-TS-029 | 없는 경로는 표준 에러 형태로 응답한다 | `test_errors.py::test_unknown_route_returns_envelope` |
| API-TS-030 | 허용되지 않은 메서드는 표준 에러 형태로 응답한다 | `test_errors.py::test_method_not_allowed_returns_envelope` |
| API-TS-031 | 처리되지 않은 예외는 내부 정보를 숨기고 표준 에러로 응답한다 | `test_errors.py::test_unhandled_exception_returns_envelope_without_leaking_details` |
| API-TS-032 | 디버그 모드에서는 처리되지 않은 예외의 상세를 담는다 | `test_errors.py::test_unhandled_exception_includes_details_in_debug_mode` |
| API-TS-033 | `ErrorCode`는 카탈로그 코드와 `HTTP_ERROR`로만 구성된다 | `test_errors.py::test_error_code_enum_matches_catalog` |
| API-TS-034 | 카탈로그 코드는 모두 `ErrorCode` 멤버다 | `test_errors.py::test_catalog_codes_are_error_code_members` |
| API-TS-035 | 대체 에러도 `ErrorCode` 안의 값을 쓴다 | `test_errors.py::test_fallback_error_stays_inside_error_code_enum` |
| API-TS-036 | 앱 코드는 raw `HTTPException`을 던지지 않는다 | `test_errors.py::test_no_raw_http_exception_is_raised_in_app_code` |
| API-TS-037 | 대체 에러는 원래 예외 문구를 노출하지 않는다 | `test_errors.py::test_fallback_error_does_not_leak_upstream_message` |
