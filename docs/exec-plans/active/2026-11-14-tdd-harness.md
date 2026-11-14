# TDD 하네스 도입

## 목표

저장소 전체에 TDD 개발 흐름(문서 → 실패하는 테스트 → 구현 → 검증)을 도입한다. 규칙 문서, 검증 스크립트, PR 자동 검증의 틀을 먼저 만들고, 첫 적용 기능으로 채팅을 개발한다. 이 단계에서는 실제 기능 코드를 작성하지 않는다.

## 산출물

| 파일 | 역할 |
|------|------|
| `AGENTS.md` (TDD 개발 규칙 섹션) | AI가 지켜야 할 개발 규칙과 문서 위치 |
| `docs/design-docs/tdd-workflow.md` | 저장소 전체 TDD 흐름과 문서·테스트 연결 규칙 |
| `docs/product-specs/chat-requirements.md` | 채팅 요구사항과 테스트 시나리오 |
| `docs/design-docs/chat-architecture.md` | 채팅 서버 구성과 의존성 규칙 |
| `tests/test_chat_service.py`, `tests/test_chat_integration.py` | 채팅 TDD 단위 테스트와 통합 테스트 자리 |
| `scripts/verify.sh` | 테스트·정적 검사 자동 실행 |
| `.github/workflows/test.yml` | PR 생성 시 자동 검증 |

## 진행 상태

- [x] 뼈대 파일 생성
- [ ] TDD 흐름 규칙 확정 (`tdd-workflow.md`)
- [ ] 정적 검사 도구 선택 (ruff 등) 후 `verify.sh`에 반영
- [ ] 채팅 요구사항·테스트 시나리오 작성
- [ ] 채팅 아키텍처·의존성 규칙 작성
- [ ] 채팅 시나리오 기반 테스트 작성 후 구현

## 검증 방법

- `scripts/verify.sh unit`이 `*_integration.py`를 제외한 테스트를 실행하고, 채팅 placeholder 테스트가 skip으로 보고된다.
- PR을 열면 `Test` 워크플로가 실행된다.

## 결정 사항

- 실제 테스트 DB 이름은 `docker-compose.test.yml`과 같은 `orderrun_test`다. `tests/conftest.py`가 `DB_NAME` 뒤에 `_test`를 붙이므로 환경 변수는 `DB_NAME=orderrun`으로 준다. (AGENTS.md, `verify.sh`, `test.yml` 반영. 첫 CI에서 `orderrun_test_test` 접속 실패로 확인)
