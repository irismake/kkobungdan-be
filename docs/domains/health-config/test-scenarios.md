# Health/Config Test Scenarios

기준 테스트 파일: `tests/test_health_integration.py`, `tests/test_config.py`

## 보장 범위

- health endpoint가 v1 `ApiResponse` 구조를 반환한다.
- OAuth/email 값 없이도 settings 객체를 구성할 수 있다.
- AWS SNS region, access key, secret key, sender id, SMS type 설정이 로드된다.

## 시나리오 목록

시나리오 ID는 테스트의 `@pytest.mark.scenario("HEALTH-TS-NNN")`와 1:1로 연결된다 ([`tdd-workflow.md`](../../design-docs/tdd-workflow.md)).

| ID | 보장 내용 | 테스트 |
|----|-----------|--------|
| HEALTH-TS-001 | 헬스체크는 v1 표준 응답 형태를 쓴다 | `test_health_integration.py::test_health_uses_v1_api_response` |
| HEALTH-TS-002 | OAuth·이메일 설정 없이 설정을 불러온다 | `test_config.py::test_settings_load_without_oauth_or_email_values` |
| HEALTH-TS-003 | AWS SNS 설정을 불러온다 | `test_config.py::test_settings_load_aws_sns_values` |
| HEALTH-TS-004 | 로그 기본값은 콘솔 출력만이다 | `test_config.py::test_settings_logging_defaults_are_console_only` |
| HEALTH-TS-005 | 운영 환경에서는 API 문서를 끈다 | `test_config.py::test_api_docs_are_disabled_in_production` |
| HEALTH-TS-006 | CORS 허용 목록은 쉼표로 나누고 공백을 지운다 | `test_config.py::test_cors_allow_origin_list_splits_and_trims` |
| HEALTH-TS-007 | CORS 허용 목록이 없으면 빈 목록이다 | `test_config.py::test_cors_allow_origin_list_is_empty_when_unset` |
| HEALTH-TS-008 | CORS 허용 출처는 설정값을 쓴다 | `test_config.py::test_cors_origins_use_configured_values` |
| HEALTH-TS-009 | 개발 환경에서 CORS 설정이 없으면 localhost를 쓴다 | `test_config.py::test_cors_origins_fall_back_to_localhost_in_development` |
| HEALTH-TS-010 | 개발 환경이 아니면 CORS 설정이 필수다 | `test_config.py::test_cors_origins_required_outside_development` |
| HEALTH-TS-011 | CORS 허용 출처에 와일드카드를 쓸 수 없다 | `test_config.py::test_cors_origins_reject_wildcard` |
| HEALTH-TS-012 | 목록에 없는 출처의 CORS 요청은 거부된다 | `test_config.py::test_cors_rejects_unlisted_origin` |
| HEALTH-TS-013 | 목록에 있는 출처의 CORS 요청은 허용된다 | `test_config.py::test_cors_allows_listed_origin` |
| HEALTH-TS-014 | 파일 로그를 켜면 날짜별 파일에 쓴다 | `test_config.py::test_setup_logging_writes_daily_file_when_enabled` |
