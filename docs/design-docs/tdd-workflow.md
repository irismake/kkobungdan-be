# TDD 개발 흐름

> 상태: 초안 (뼈대만 작성됨)
> 관련 문서: [`../references/testing-guidelines.md`](../references/testing-guidelines.md), [`testing-conventions.md`](./testing-conventions.md), [`../HARNESS_ENGINEERING.md`](../HARNESS_ENGINEERING.md)

## 배경

<!-- 현재 저장소는 구현 후 테스트를 보강하는 방식이다. TDD를 저장소 전체 규칙으로 도입하는 이유를 적는다. -->

## 적용 범위

- 새 기능, 버그 수정, 동작이 바뀌는 리팩터링은 모두 이 흐름을 따른다.
- 기존 테스트가 없는 코드를 수정할 때의 처리: TODO
- 예외 (문서만 변경, 설정만 변경 등): TODO

## 개발 흐름

하네스 엔지니어링의 문서 → 계획 → 코드 → 검증 순서 안에서 코드 단계를 Red → Green → Refactor로 진행한다.

1. **문서**: `docs/product-specs/`에 요구사항(`{DOMAIN}-REQ-*`)과 테스트 시나리오(`{DOMAIN}-TS-*`)를 적는다.
2. **Red**: 시나리오마다 실패하는 테스트를 먼저 작성하고, 실패를 확인한다.
3. **Green**: 테스트를 통과하는 최소한의 코드를 작성한다.
4. **Refactor**: 테스트를 유지한 채 구조를 정리한다.
5. **검증**: `scripts/verify.sh`가 통과해야 완료로 본다.

## 문서와 테스트 연결

- 시나리오 ID 규칙: TODO (예: `CHAT-TS-001`)
- 테스트에 시나리오 ID를 남기는 방식: TODO (docstring 첫 줄 / pytest marker 등)
- 시나리오 표에 테스트 위치를 적는다.

## 테스트 종류와 위치

기존 [`testing-guidelines.md`](../references/testing-guidelines.md)의 분류와 파일명 규칙을 따른다.

| 종류 | 파일명 | DB | `verify.sh` 대상 |
|------|--------|----|------------------|
| 단위 | `tests/test_{module}.py` | 불필요 | `unit` |
| 통합 | `tests/test_{domain}_integration.py` | MySQL 필요 | `integration` |

## 커밋과 PR 규칙

- TODO: Red/Green 커밋을 나누는지 여부
- TODO: PR에 테스트가 없을 때 처리
- PR을 열면 [`.github/workflows/test.yml`](../../.github/workflows/test.yml)이 `scripts/verify.sh all`을 실행한다.

## 기존 코드 전환 계획

- TODO: 기존 테스트에 시나리오 ID 연결
- TODO: 정적 검사 도구 도입

## 대안과 결정

| 대안 | 장점 | 단점 | 결정 |
|------|------|------|------|
| TODO | | | |
