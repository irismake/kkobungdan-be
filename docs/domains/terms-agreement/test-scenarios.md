# Terms Agreement Test Scenarios

기준 테스트 파일: `tests/test_terms_agreement_integration.py`

## 보장 범위

- 약관 동의 생성과 갱신이 같은 사용자 기준으로 동작한다.
- 잘못된 요청은 validation error 계약을 따른다.
- 인증 누락 또는 잘못된 인증은 인증 error 계약을 따른다.
- 약관 동의 모델 필드와 문서 스펙이 일치하는지 확인한다.

## 시나리오 목록

시나리오 ID는 테스트의 `@pytest.mark.scenario("TERMS-TS-NNN")`와 1:1로 연결된다 ([`tdd-workflow.md`](../../design-docs/tdd-workflow.md)).

| ID | 보장 내용 | 테스트 |
|----|-----------|--------|
| TERMS-TS-001 | 약관 동의를 생성하고 갱신한다 | `test_terms_agreement_integration.py::test_terms_agreement_create_and_update` |
| TERMS-TS-002 | 약관 동의의 입력값 오류는 거부된다 | `test_terms_agreement_integration.py::test_terms_agreement_validation_errors` |
| TERMS-TS-003 | 약관 동의 API는 인증이 필요하다 | `test_terms_agreement_integration.py::test_terms_agreement_auth_errors` |
| TERMS-TS-004 | 약관 동의 ORM 모델이 문서의 스펙과 같다 | `test_terms_agreement_integration.py::test_terms_agreement_model_spec_matches_docs` |
