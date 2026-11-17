# Settlement Account Test Scenarios

기준 테스트 파일: `tests/test_settlement_integration.py`

## 보장 범위

- 미등록 계좌 조회는 성공 응답 안에 null 데이터를 반환한다.
- 저장 후 같은 API로 계좌 정보를 수정할 수 있다.
- 인증된 사용자는 정산 계좌 등록에 사용할 은행명 목록을 조회할 수 있다.
- 필수 필드, 형식 validation, 인증 실패를 검증한다.
- 계좌가 없는 사용자는 Proposal을 생성할 수 없고 `409 SETTLEMENT_ACCOUNT_REQUIRED`를 받는다.
- 계좌가 없는 꼬붕은 Offer를 생성할 수 없고 `409 SETTLEMENT_ACCOUNT_REQUIRED`를 받는다.

## 시나리오 목록

시나리오 ID는 테스트의 `@pytest.mark.scenario("SETTLEMENT-TS-NNN")`와 1:1로 연결된다 ([`tdd-workflow.md`](../../design-docs/tdd-workflow.md)).

| ID | 보장 내용 | 테스트 |
|----|-----------|--------|
| SETTLEMENT-TS-001 | 정산 계좌가 없으면 조회 결과는 null이다 | `test_settlement_integration.py::test_get_settlement_account_returns_null_when_missing` |
| SETTLEMENT-TS-002 | 정산 계좌를 저장하고 수정한다 | `test_settlement_integration.py::test_save_and_update_settlement_account` |
| SETTLEMENT-TS-003 | 은행 목록은 인증이 필요하고 지원 은행 이름을 반환한다 | `test_settlement_integration.py::test_get_settlement_bank_names_requires_auth_and_returns_supported_names` |
| SETTLEMENT-TS-004 | 정산 계좌 API는 인증과 입력값을 검증한다 | `test_settlement_integration.py::test_settlement_account_validation_and_auth` |
| SETTLEMENT-TS-005 | 정산 계좌는 제거된 필드와 지원하지 않는 은행을 거부한다 | `test_settlement_integration.py::test_settlement_account_rejects_removed_fields_and_unsupported_bank` |
| SETTLEMENT-TS-006 | 정산 계좌는 예금주가 필수다 | `test_settlement_integration.py::test_settlement_account_requires_account_holder` |
