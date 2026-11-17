# TDD 하네스 도입

## 목표

저장소 전체에 TDD 개발 흐름(문서 → 실패하는 테스트 → 구현 → 검증)을 도입한다. 규칙 문서, 검증 스크립트, PR 자동 검증의 틀을 먼저 만들고, 첫 적용 기능으로 채팅을 개발한다. 이 단계에서는 실제 기능 코드를 작성하지 않는다.

## 산출물

| 파일 | 역할 |
|------|------|
| `AGENTS.md` (TDD 개발 규칙 섹션) | AI가 지켜야 할 개발 규칙과 문서 위치 |
| `docs/design-docs/tdd-workflow.md` | 저장소 전체 TDD 흐름과 문서·테스트 연결 규칙 |
| `docs/product-specs/chat-requirements.md` | 채팅 요구사항 |
| `docs/domains/chat/test-scenarios.md` | 채팅 테스트 시나리오 |
| `docs/design-docs/chat-architecture.md` | 채팅 서버 구성과 의존성 규칙 |
| `tests/test_chat_service.py`, `tests/test_chat_integration.py` | 채팅 TDD 단위 테스트와 통합 테스트 자리 |
| `scripts/verify.sh` | 테스트·정적 검사 자동 실행 |
| `scripts/check_scenarios.py` | 시나리오 표와 테스트 marker의 1:1 연결 검사 (`verify.sh static`) |
| `pyproject.toml` (`scenario` marker, `--strict-markers`) | 테스트에 시나리오 ID를 붙이는 marker |
| `docs/domains/*/test-scenarios.md` "시나리오 목록" | 기존 테스트 311개의 시나리오 ID 표 |
| `.github/pull_request_template.md` "테스트" 칸 | PR의 연결 시나리오와 테스트 없는 이유 |
| `.github/workflows/test.yml` | PR·staging 머지 시 자동 검증. 변경 파일과 Draft 여부로 검사 강도를 나누고, staging 머지에서 성공하면 배포를 부름 |
| `.github/workflows/staging-deploy.yml` | staging push 트리거 제거, `workflow_call`·`workflow_dispatch`만 남김, 배포 동시 실행 묶음 추가 |

## 진행 상태

- [x] 뼈대 파일 생성
- [x] TDD 흐름 규칙 확정 (`tdd-workflow.md`, AGENTS.md)
- [x] 시나리오 ID marker와 연결 검사 추가, 기존 테스트 311개에 시나리오 ID 연결
- [x] CI 실행 정책 적용: Draft는 정적+단위, 일반 PR·staging 머지는 전체, 모델·마이그레이션 변경은 빈 DB 마이그레이션 검사 추가
- [x] staging 배포를 CI 성공 뒤로 연결: `staging-deploy.yml`을 `workflow_call`로 바꾸고 `test.yml`의 `Staging 배포` Job이 부름
- [x] 단위·통합 분류를 `db` fixture 의존 기준으로 변경 (`tests/conftest.py`)
- [x] 정적 검사 도구(ruff)는 다음 작업으로 넘김 ([`TD-022`](../tech-debt-tracker.md))
- [x] 채팅 요구사항·시나리오·아키텍처·구현은 채팅 작업(`feature/chat`)으로 넘김. 이 브랜치에는 채팅 문서와 테스트 자리 뼈대만 둔다

## 검증 방법

- `scripts/verify.sh unit`이 `*_integration.py`를 제외한 테스트를 실행하고, 채팅 placeholder 테스트가 skip으로 보고된다.
- PR을 열면 `Test` 워크플로가 실행된다.
- 워크플로 3개(`test.yml`, `staging-deploy.yml`, `production-deploy.yml`)가 `actionlint`를 통과한다 (로컬, shellcheck 제외).
- 배포 연결은 실제 실행으로만 확인된다: Draft PR에서 `Staging 배포` Job이 없음, staging 머지에서 CI 실패 시 건너뜀, 성공 시 실행. #6 머지 후 첫 staging push에서 확인한다.
- `scripts/verify.sh unit`이 MySQL 없이 93개 통과, 2개 건너뜀(채팅 테스트 자리)으로 끝난다 (로컬에서 확인).
- `scripts/verify.sh static`의 시나리오 연결 검사가 "시나리오 313개 중 313개가 테스트에 연결됨 (경고 0, 오류 0)"을 출력한다. 테스트의 ID를 문서에 없는 값으로 바꾸면 오류로 실패한다 (로컬에서 확인).

## 결정 사항

- 실제 테스트 DB 이름은 `docker-compose.test.yml`과 같은 `orderrun_test`다. `tests/conftest.py`가 `DB_NAME` 뒤에 `_test`를 붙이므로 환경 변수는 `DB_NAME=orderrun`으로 준다. (AGENTS.md, `verify.sh`, `test.yml` 반영. 첫 CI에서 `orderrun_test_test` 접속 실패로 확인)
- PR 자동 검증 첫 실행에서 드러난 기존 실패 `test_create_proposal_validation_errors`(TD-010)는 테스트에 정산 계좌를 준비하는 방식으로 해결하고 트래커에서 제거했다. 서비스의 검사 순서(정산 계좌 → 입력값)는 바꾸지 않았다.
- 시나리오는 `docs/domains/{domain}/test-scenarios.md`에 두고 테스트와 `@pytest.mark.scenario` marker로 1:1 연결한다. 규칙 전체는 `tdd-workflow.md`에 정리했다 (2026-11-17).
- TDD 흐름은 채팅과 새 기능에 적용한다. 기존 기능은 시나리오를 새로 설계하지 않고 기존 테스트에 ID만 붙였다.
