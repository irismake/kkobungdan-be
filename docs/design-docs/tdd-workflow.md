# TDD 개발 흐름

> 상태: 확정 (2026-11-17)
> 관련 문서: [`../references/testing-guidelines.md`](../references/testing-guidelines.md), [`testing-conventions.md`](./testing-conventions.md), [`../HARNESS_ENGINEERING.md`](../HARNESS_ENGINEERING.md)

## 배경

지금까지는 구현한 뒤 테스트를 보강했다. 그래서 테스트가 무엇을 보장하는지는 도메인 문서의 문장으로만 남았고, 문서와 테스트가 맞는지 확인할 방법이 없었다. 예를 들어 요청 목록 정렬처럼 문서와 테스트가 서로 다른 내용을 말해도 알아채지 못했다.

TDD 흐름에서는 시나리오를 먼저 문서에 적고, 시나리오마다 실패하는 테스트를 만든 뒤 구현한다. 시나리오와 테스트를 ID로 1:1 연결하고, 그 연결을 `scripts/verify.sh`가 매번 검사한다.

## 적용 범위

- TDD 흐름(문서 → Red → Green → Refactor)은 채팅부터 적용하고, 앞으로 새로 만드는 기능에 적용한다.
- 기존 기능은 이미 테스트가 있으므로 시나리오를 새로 설계하지 않는다. 기존 테스트에는 시나리오 ID만 붙였다(아래 [기존 테스트 전환](#기존-테스트-전환)).
- 새 기능이 기존 코드를 바꾸는데 그 동작에 테스트가 없으면, 바꿀 동작에 대해서만 시나리오와 실패하는 테스트를 먼저 쓰고 고친다. 주변 코드 전체를 테스트로 덮을 필요는 없다.

## 개발 흐름

하네스 엔지니어링의 문서 → 계획 → 코드 → 검증 순서 안에서 코드 단계를 Red → Green → Refactor로 진행한다.

1. **문서**: `docs/product-specs/`에 요구사항(`{DOMAIN}-REQ-*`)을, `docs/domains/{domain}/test-scenarios.md`에 테스트 시나리오(`{DOMAIN}-TS-*`)를 적는다. 시나리오마다 연결된 요구사항 ID를 적는다.
2. **Red**: 시나리오마다 실패하는 테스트를 먼저 작성하고, 실패를 확인한다.
3. **Green**: 테스트를 통과하는 최소한의 코드를 작성한다.
4. **Refactor**: 테스트를 유지한 채 구조를 정리한다.
5. **검증**: `scripts/verify.sh`가 통과해야 완료로 본다.

## 문서와 테스트 연결

### 시나리오 ID

- 형식은 `{DOMAIN}-TS-{3자리 번호}`다. 예: `CHAT-TS-001`
- 번호는 도메인 안에서 순서대로 붙이고, 한 번 쓴 번호는 다른 시나리오에 다시 쓰지 않는다. 시나리오를 지우면 그 번호는 비워 둔다.
- 도메인 접두어:

| 접두어 | 도메인 문서 |
|--------|-------------|
| `PROPOSAL` | [`../domains/proposal/test-scenarios.md`](../domains/proposal/test-scenarios.md) |
| `OFFER` | [`../domains/offer/test-scenarios.md`](../domains/offer/test-scenarios.md) |
| `AUTH` | [`../domains/user-auth/test-scenarios.md`](../domains/user-auth/test-scenarios.md) |
| `TERMS` | [`../domains/terms-agreement/test-scenarios.md`](../domains/terms-agreement/test-scenarios.md) |
| `SETTLEMENT` | [`../domains/settlement/test-scenarios.md`](../domains/settlement/test-scenarios.md) |
| `NOTI` | [`../domains/notification/test-scenarios.md`](../domains/notification/test-scenarios.md) |
| `ADMIN` | [`../domains/admin-payment-settlement/test-scenarios.md`](../domains/admin-payment-settlement/test-scenarios.md) |
| `API` | [`../domains/api-contract/test-scenarios.md`](../domains/api-contract/test-scenarios.md) |
| `HEALTH` | [`../domains/health-config/test-scenarios.md`](../domains/health-config/test-scenarios.md) |
| `CHAT` | [`../domains/chat/test-scenarios.md`](../domains/chat/test-scenarios.md) |

새 도메인을 만들면 이 표에 접두어를 추가한다.

### 테스트에 ID 남기기

테스트 함수에 `scenario` marker를 붙인다. marker는 `pyproject.toml`에 등록되어 있고 `--strict-markers`로 오타를 막는다.

```python
@pytest.mark.scenario("CHAT-TS-001")
def test_create_offer_creates_active_chat_room(client, db, factory):
    ...
```

- 시나리오 하나는 테스트 함수 하나와 연결한다. 여러 경우를 확인하는 시나리오는 `parametrize`로 한 함수 안에서 나눈다.
- 특정 시나리오의 테스트는 시나리오 표의 테스트 위치(`파일::함수`)로 찾아 실행한다. 예: `pytest tests/test_offer_integration.py::test_cancel_offer_author_and_status_rules`

### 시나리오 표

- 새 기능(채팅 등): `| ID | 요구사항 | 시나리오 (Given / When / Then) | 종류 | 테스트 위치 |`
- 기존 도메인: `| ID | 보장 내용 | 테스트 |`. 요구사항 ID가 없는 기존 기능이라 요구사항 칸은 두지 않는다.

### 연결 검사

`scripts/verify.sh static`(과 `all`)이 [`scripts/check_scenarios.py`](../../scripts/check_scenarios.py)로 다음을 검사한다. 테스트를 import하지 않고 읽으므로 DB가 필요 없다.

1. 테스트에 붙은 ID는 모두 시나리오 표에 있다.
2. 한 ID는 테스트 하나에만 붙는다.
3. 시나리오 표의 ID는 중복되지 않는다.
4. 시나리오 표의 ID는 모두 테스트에 연결된다. 단, 문서 상단 `> 상태:`에 `구현 전`이 있으면 테스트가 없는 ID는 경고로만 알린다. 문서 단계(시나리오만 쓰고 테스트를 아직 쓰지 않은 상태)를 허용하기 위해서다. 구현이 끝나면 상태에서 `구현 전`을 지워 검사를 강제한다.

### 보류 테스트

다른 작업이 끝나야 활성화할 수 있는 시나리오(예: 차단 구현 뒤에 확인할 채팅 시나리오)는 테스트를 쓰고 `skip`으로 둔다. 이유에 조건을 적는다.

```python
@pytest.mark.scenario("CHAT-TS-029")
@pytest.mark.skip(reason="사용자 차단 구현 후 활성화 (user-block.md)")
def test_blocked_room_rejects_messages_from_both_sides(...):
    ...
```

skip은 pytest 결과의 skip 목록에 남으므로 조건이 풀리면 찾아서 활성화한다.

## 테스트 종류와 위치

기존 [`testing-guidelines.md`](../references/testing-guidelines.md)의 분류와 파일명 규칙을 따른다.

| 종류 | 파일명 | DB | `verify.sh` 대상 |
|------|--------|----|------------------|
| 단위 | `tests/test_{module}.py` | 불필요 | `unit` (`integration` 표시가 없는 테스트) |
| 통합 | `tests/test_{domain}_integration.py` | MySQL 필요 | `integration` (전체 테스트) |

단위·통합은 파일 이름이 아니라 실제 DB 사용으로 나눈다. `tests/conftest.py`가 `db` fixture에 의존하는 테스트(`client`, `factory` 포함)에 `integration` 표시를 자동으로 붙이고, `verify.sh unit`은 `-m "not integration"`으로 나머지만 돌린다. 그래서 단위 파일 안에 DB 테스트가 있어도 DB 없는 검사에서 깨지지 않는다.

| `verify.sh` 대상 | 하는 일 | 필요한 것 |
|------------------|---------|-----------|
| `static` | `compileall`, 시나리오 연결 검사 | Python만 |
| `unit` | 단위 테스트 | 의존성 설치 |
| `integration` | 전체 테스트 | 의존성, MySQL |
| `migration` | 빈 DB(`orderrun_migration_check`)에 `alembic upgrade head` | 의존성, MySQL, 빈 DB |
| `all` (기본) | `static` + `integration` | 의존성, MySQL |

## 커밋과 PR 규칙

- 브랜치 안에서는 Red 커밋(`test:`)과 Green 커밋(`feat:`/`fix:`)을 나눈다. 리뷰어가 테스트가 먼저 있었는지 볼 수 있게 하기 위해서다. staging에는 squash merge하므로 최종 이력에는 하나로 합쳐진다.
- Red 커밋은 테스트가 실패하는 상태라 CI 대상이 아니다. CI는 PR의 최신 커밋을 검사한다.
- 동작을 바꾸는 PR은 본문의 "연결된 시나리오"에 시나리오 ID를 적는다. 테스트가 없으면 "테스트 없는 이유"를 적고, 리뷰어가 받아들일지 판단한다. CI로 자동 차단하지는 않는다.
- PR 검사는 아래 [CI 실행 정책](#ci-실행-정책)을 따른다. 머지 전에 PR 화면의 `CI 결과`가 통과인지 확인한다. 저장소 요금제 때문에 필수 검사(branch protection)를 걸 수 없어서 실패해도 머지 버튼은 막히지 않는다.

## CI 실행 정책

[`.github/workflows/test.yml`](../../.github/workflows/test.yml)은 PR마다 실행하되, 상황에 따라 검사 강도를 다르게 한다. 목표는 개발 중에는 빠른 피드백을, 머지 전과 머지 후에는 전체 검증을 보장하는 것이다.

| 상황 | 실행하는 검사 |
|------|---------------|
| Draft PR에 코드 푸시 | 정적 검사 + 단위 테스트 |
| 일반 PR에 코드 푸시 | 정적 검사 + 단위 테스트 + 전체 테스트(MySQL) |
| Draft → Ready for review | 일반 PR과 같다 (`ready_for_review` 이벤트) |
| 코드와 무관한 파일만 변경 (문서, `nginx/` 등) | 정적 검사만 (시나리오 연결 검사 포함) |
| DB 모델·마이그레이션 변경 (`app/models/`, `alembic/`) | 위 검사 + 빈 DB 마이그레이션 검사 (Draft가 아닐 때) |
| staging에 머지 (push) | 변경 파일과 관계없이 전부 (정적·단위·전체 테스트·마이그레이션). 모두 성공하면 staging 배포 |
| 같은 PR에 연속 푸시 | 이전 실행을 취소하고 최신 커밋만 검사 (`concurrency`) |

- 워크플로 자체를 `paths` 필터로 건너뛰지 않는다. 워크플로는 항상 실행하고, `변경 파일 확인` Job이 바뀐 파일을 보고 필요한 Job만 실행한다. 워크플로가 통째로 건너뛰어지면 결과가 PR에 남지 않기 때문이다.
- "코드에 영향을 주는 파일"은 `app/`, `tests/`, `alembic/`, `alembic.ini`, `pyproject.toml`, `setup.py`, `scripts/verify.sh`, `scripts/check_scenarios.py`, `docker-compose.test.yml`, `.github/workflows/test.yml`이다. 이 중 하나라도 바뀌면 테스트를 돌린다.
- PR 판정은 마지막 `CI 결과` Job 하나로 본다. 건너뛴 Job은 그 검사가 필요 없는 변경이라 통과로 보고, 실패하거나 취소된 Job이 있으면 실패다. 나중에 필수 검사를 걸 수 있게 되면 이 Job 하나만 필수로 지정한다.
- staging 배포는 CI 뒤에 붙어 있다. `staging-deploy.yml`은 staging push로 직접 실행되지 않고, staging 머지에서 `CI 결과`가 성공일 때 `Staging 배포` Job이 `workflow_call`로 부른다(`secrets: inherit`). CI가 실패하거나 취소되면 배포 Job은 건너뛴다. 수동 재배포는 지금처럼 `workflow_dispatch`로 한다.
- 같은 커밋을 두 번 배포하지 않도록, staging push의 CI 실행은 취소하지 않고 차례로 돌린다(배포 도중 취소되면 마이그레이션이 끊긴다). 배포 Job에는 `staging-deploy` 동시 실행 묶음을 걸어 CI 배포와 수동 배포가 겹치지 않게 했다. 이미 `main`에 있는 커밋을 건너뛰는 기존 `check` 가드는 그대로다.
- `scripts/verify.sh`나 `test.yml`이 바뀐 PR도 마이그레이션 검사를 돌린다. staging 배포를 막을 수 있는 검사를 머지 전에 한 번은 돌려 보기 위해서다.
- 운영 배포(`production-deploy.yml`, main push)는 바꾸지 않았다.
- `nginx/` 설정 검사와 린터(ruff)는 아직 없다 ([`TD-022`](../exec-plans/tech-debt-tracker.md)). 생기면 정적 검사 Job에 넣는다.

## 기존 테스트 전환

- 2026-11-17에 기존 테스트 311개에 도메인별 시나리오 ID를 붙였다. 각 도메인 `test-scenarios.md`의 "시나리오 목록" 표가 테스트 함수와 1:1로 연결된다.
- 기존 문서의 "보장 범위" 문장은 그대로 두었다. 문장과 표가 다르면 표(테스트)가 실제 보장 범위다.
- 문서에 기준 테스트 파일로 적혀 있지 않던 파일은 가까운 도메인에 넣었다: `test_proposal_report_integration.py` → PROPOSAL, `test_phone_verification.py` → AUTH, `test_admin_auth_integration.py`·`test_dispute_survey_integration.py`·`test_dispute_evidence_integration.py` → ADMIN.
- 정적 검사 도구(ruff 등) 도입은 다음 작업으로 미룬다 ([`TD-022`](../exec-plans/tech-debt-tracker.md)).

## 대안과 결정

| 대안 | 장점 | 단점 | 결정 |
|------|------|------|------|
| 시나리오를 요구사항 문서(`product-specs`)에 함께 둔다 | 요구사항과 시나리오를 한 파일에서 본다 | 기존 도메인 시나리오 문서(`docs/domains`)와 위치가 갈린다 | 채택하지 않음. 시나리오는 `docs/domains/{domain}/test-scenarios.md`에 둔다 |
| 시나리오 ID를 docstring 첫 줄에 적는다 | 간단하다 | 기계적으로 고르거나 검사하기 어렵다 | 채택하지 않음 |
| 시나리오 ID를 테스트 함수 이름에 넣는다 | 별도 장치가 없다 | 이름이 길어지고 번호를 바꾸면 이름도 바꿔야 한다 | 채택하지 않음 |
| `@pytest.mark.scenario` marker | 고르기·검사가 쉽다 | marker 등록과 검사 스크립트가 필요하다 | **채택** |
| 보류 테스트를 `xfail(strict)`로 둔다 | 구현되면 CI가 알려준다 | 구현이 없으면 import 단계에서 깨져 다루기 어렵다 | 채택하지 않음. `skip` + 조건 |
| 테스트 없는 PR을 CI로 막는다 | 강제력이 있다 | 문구만 바꾸는 PR처럼 예외가 잦아 우회 장치가 필요하다 | 채택하지 않음. PR 본문과 리뷰로 거른다 |
| Draft PR은 CI를 전부 건너뛴다 | 실행 횟수가 가장 적다 | TDD 중에 실패를 늦게 안다 | 채택하지 않음. Draft에서도 정적 검사와 단위 테스트는 돌린다 |
| `paths-ignore`로 워크플로를 건너뛴다 | 설정이 간단하다 | 검사 결과가 PR에 남지 않고, 필수 검사를 걸면 대기 상태로 머지를 막는다 | 채택하지 않음. 워크플로는 항상 돌리고 Job 단위로 건너뛴다 |
| staging 배포를 push로 따로 돌린다 | 기존 구조 그대로다 | CI가 실패해도 배포된다 | 채택하지 않음. 배포를 CI의 마지막 Job으로 `workflow_call` 한다 |
| 단위·통합을 파일 이름(`*_integration.py`)으로 나눈다 | 규칙이 단순하다 | 단위 파일 안의 DB 테스트 3개가 DB 없는 검사에서 깨졌다 | 채택하지 않음. `db` fixture 의존으로 자동 분류한다 |
