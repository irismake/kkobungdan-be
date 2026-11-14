# OrderRun-BE 작업 가이드

## 목적

이 저장소는 문서를 중심으로 설계, 계획, 구현 방향을 관리하는 엔지니어링 하네스를 사용한다.
코드 작업이 커지기 전에 관련 문서 위치와 기준 문서를 먼저 확인한다.

## 운영 원칙

- 다음 단계가 저위험이고 되돌릴 수 있다면 직접 진행한다.
- 변경은 작고 검토 가능하게 유지하고, 가능한 한 문서나 계획에 연결한다.
- 추정보다 근거를 우선한다. 결정이 바뀌면 관련 기준 문서를 함께 갱신한다.
- 새 추상화를 만들기 전에 기존 패턴과 구조를 재사용한다.
- 완료 주장은 변경 크기에 맞는 최소 검증 근거와 함께 한다.

## 기준 문서 맵

### 하네스 엔지니어링 핵심
- [`docs/HARNESS_ENGINEERING.md`](./docs/HARNESS_ENGINEERING.md): 문서 중심 개발 방법론
- [`docs/DIRECTORY_STRUCTURE.md`](./docs/DIRECTORY_STRUCTURE.md): 디렉토리 구조와 책임
- [`docs/ITERATION_FRAMEWORK.md`](./docs/ITERATION_FRAMEWORK.md): 반복 개선 프레임워크

### 시스템과 작업 규칙
- [`ARCHITECTURE.md`](./ARCHITECTURE.md): 시스템 개요와 문서 진입점
- [`docs/DESIGN.md`](./docs/DESIGN.md): 설계 문서 작성 규칙
- [`docs/PLANS.md`](./docs/PLANS.md): 실행 계획 운영 방식
- [`docs/PRODUCT_SENSE.md`](./docs/PRODUCT_SENSE.md): 제품 우선순위 판단 기준
- [`docs/QUALITY_SCORE.md`](./docs/QUALITY_SCORE.md): 품질 평가 기준
- [`docs/references/testing-guidelines.md`](./docs/references/testing-guidelines.md): 테스트 작성 기준
- [`docs/RELIABILITY.md`](./docs/RELIABILITY.md): 신뢰성 기준
- [`docs/SECURITY.md`](./docs/SECURITY.md): 보안 기준

## 작업 규칙

- 새 기능 작업은 가능하면 `docs/product-specs/`의 명시적 스펙과 연결한다.
- 구조적이거나 장기 영향이 큰 결정은 `docs/design-docs/`에 남긴다.
- 진행 중 작업은 `docs/exec-plans/active/`, 완료된 작업은 `docs/exec-plans/completed/`로 관리한다.
- 코드나 설계로부터 파생된 산출물은 `docs/generated/`에 둔다.
- 외부 도구, 플랫폼, 참고 자료 메모는 `docs/references/`에 둔다.

## TDD 개발 규칙

모든 기능 개발과 동작 변경은 문서 → 실패하는 테스트(Red) → 구현(Green) → 정리(Refactor) → 검증 순서로 진행한다. 세부 규칙은 작성 중이다.

### 문서 위치
- [`docs/design-docs/tdd-workflow.md`](./docs/design-docs/tdd-workflow.md): TDD 흐름과 문서·테스트 연결 규칙
- [`docs/references/testing-guidelines.md`](./docs/references/testing-guidelines.md): 테스트 종류, 파일명, 검증 규칙
- `docs/product-specs/*.md`: 기능별 요구사항과 테스트 시나리오
- `tests/`: 단위 테스트(`test_{module}.py`)와 통합 테스트(`test_{domain}_integration.py`)
- [`scripts/verify.sh`](./scripts/verify.sh): 테스트·정적 검사 자동 실행
- [`.github/workflows/test.yml`](./.github/workflows/test.yml): PR 생성 시 자동 검증

### 규칙
- 요구사항(`{DOMAIN}-REQ-*`)과 테스트 시나리오(`{DOMAIN}-TS-*`)를 먼저 스펙 문서에 적는다.
- 시나리오마다 실패하는 테스트를 먼저 작성하고 실패를 확인한 뒤 구현한다.
- 완료 전 `scripts/verify.sh`가 통과해야 한다.
- TODO: 추가 규칙

### 채팅 (첫 적용 기능)
- [`docs/product-specs/chat-requirements.md`](./docs/product-specs/chat-requirements.md): 채팅 요구사항과 테스트 시나리오
- [`docs/design-docs/chat-architecture.md`](./docs/design-docs/chat-architecture.md): 채팅 서버 구성과 의존성 규칙

## 마이그레이션 규칙

- Alembic revision ID는 현재 저장소처럼 설명형 이름을 사용할 수 있다.
- fresh MySQL DB의 `alembic_version.version_num`은 `varchar(255)`로 생성되도록 `alembic/env.py`에서 보장한다.
- 로컬 fresh MySQL DB도 `alembic upgrade head`로 초기 세팅 가능해야 한다.
- 현재 모델 기준 baseline 이후에 컬럼/인덱스를 추가하는 migration은 이미 존재할 때 실패하지 않도록 작성한다.
- 기존 DB의 `alembic_version` 테이블은 자동 변경하지 않는다.

## 브랜치 동기화 규칙

- `feature/*`, `fix/*` 브랜치는 최신 `staging`에서 만든다.
- `feature/*`, `fix/*` → `staging`은 squash merge한다. 작업 브랜치의 중간 커밋은 하나의 검토 가능한 변경으로 정리한다.
- `staging` → `main`은 merge commit으로 반영한다. `staging`의 커밋 계보와 릴리스 경계를 유지하기 위해 squash merge나 rebase merge를 사용하지 않는다.
- 릴리스 후 `main` → `staging` 동기화는 평소 수행하지 않는다. `staging` 커밋이 merge commit을 통해 이미 `main` 이력에 포함되므로 merge, rebase, reset/force push가 필요하지 않다.
- 일반 기능과 수정 사항을 `main`에 직접 커밋하지 않는다.
- 긴급 수정도 가능하면 `fix/*` → `staging` → `main` 흐름을 따른다. 아직 릴리스할 수 없는 변경이 `staging`에 있어 운영만 즉시 수정해야 한다면 `main`에서 hotfix 브랜치를 만들어 반영한 뒤, 같은 수정을 별도 `fix/*` PR로 `staging`에 반영한다.
- `.github/workflows/staging-deploy.yml`의 커밋 도달성 가드는 예외 상황에서 이미 `main`에 포함된 커밋의 중복 배포를 막는 안전망으로 유지한다. 명시적으로 재배포할 때는 `workflow_dispatch`를 사용한다.
- 예외적으로 `staging` → `main`을 squash merge했다면 두 브랜치의 커밋 계보가 갈라지므로 `git fetch origin` 후 `staging`에서 `git reset --hard origin/main`, `git push --force-with-lease origin staging` 순서로 동기화한다. 이 push는 Staging Deploy 워크플로를 트리거하지만, 커밋 도달성 가드가 이미 `main`에 포함된 커밋임을 확인하므로 `check` job만 실행되고 이미지 재빌드와 배포는 건너뛴다.

## 테스트 실행 규칙

- 통합 테스트를 실행할 때는 `docker-compose.test.yml`의 `mysql-test` 서비스를 사용한다.
- 테스트 DB는 `docker compose -f docker-compose.test.yml up -d mysql-test`로 띄우고, `orderrun-mysql-test`가 `healthy`인지 확인한 뒤 `pytest`를 실행한다.
- 테스트 실행 env는 compose 설정과 맞춘다: `DB_HOST=127.0.0.1`, `DB_PORT=3307`, `DB_USERNAME=orderrun_user`, `DB_PASSWORD=orderrun_pass`, `DB_NAME=orderrun_test`.
- 통합 테스트 실패를 로컬 MySQL 인증/스키마 문제로 판단하기 전에 위 테스트 compose 환경으로 재실행한다.

## 완료 전 확인

1. 관련 문서 엔트리가 존재하거나 갱신되었는지 확인한다.
2. 상위 문서 간 링크가 깨지지 않았는지 확인한다.
3. 남은 리스크와 후속 작업이 계획 또는 트래커에 기록되었는지 확인한다.
