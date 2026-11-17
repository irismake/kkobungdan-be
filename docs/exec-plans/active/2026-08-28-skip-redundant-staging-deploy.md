# 동기화 push가 스테이징을 재배포하지 않게 한다

> 2026-11-17 변경: Staging Deploy는 더 이상 `push: staging`으로 직접 실행되지 않는다. staging push는 CI(`test.yml`)를 실행하고, CI가 성공하면 `workflow_call`로 Staging Deploy를 부른다. 아래 `check` 가드는 그대로 동작한다 ([`tdd-workflow.md` CI 실행 정책](../../design-docs/tdd-workflow.md#ci-실행-정책)).

작성일: 2026-08-28 · 상태: 구현·검증 완료, 다음 릴리스 동기화에서 실동작 확인 대기

## 배경

릴리스 한 번에 스테이징 배포가 두 번 돈다.

| 단계 | 트리거 | 배포 | 필요한가 |
| --- | --- | --- | --- |
| feature → `staging` | `push: staging` | Staging Deploy | 필요 |
| `staging` → `main` (squash) | `push: main` | Production Deploy | 필요 |
| `main` → `staging` (reset) | `push: staging` | Staging Deploy | **불필요** |

3번은 [AGENTS.md "브랜치 동기화 규칙"](../../../AGENTS.md)이 정한 `git reset --hard main` +
force push다. 트리 내용이 `main`과 완전히 같아 **방금 프로덕션에 나간 것과 동일한 내용을
스테이징에 다시 배포한다.**

게다가 2번(프로덕션)과 3번이 거의 동시에 돈다. `orderrun-app-prod` 컨테이너가 스테이징
박스에도 떠 있는 것을 확인했으므로 두 배포가 같은 EC2를 만질 가능성이 있고, 그렇다면
`docker pull`·`docker image prune`이 겹친다. 단순 낭비가 아니라 경합이다.

## 왜 `[skip ci]`가 안 되는가

`git reset --hard main`은 **새 커밋을 만들지 않는다.** 포인터만 옮기므로 push 후 `staging`의
HEAD는 `main`의 스쿼시 커밋 그 자체다. `[skip ci]`를 넣을 새 커밋이 없고, 그 스쿼시 커밋에
넣으면 프로덕션 배포까지 함께 건너뛴다.

`rebase`로 바꿔도 무의미하다. 원격 `staging`을 갱신하려면 push해야 하고, `push: staging`은
어떤 방식이든 트리거된다.

## 결정: 커밋 도달성으로 판정한다

워크플로 앞에 `check` job을 두고 **"push된 커밋이 이미 `main`에 있는가"**를 본다.

```
git merge-base --is-ancestor $GITHUB_SHA origin/main
```

- **참** — `staging`이 `main`에 없는 것을 하나도 안 갖고 있다. 정의상 동기화 push다. 건너뛴다
- **거짓** — 기능 커밋이 쌓여 있다. 정상 배포한다

트리 비교(`git diff`)가 아니라 **커밋 도달성**으로 판정하는 이유는, 우연히 내용이 같아진
서로 다른 커밋과 동기화 push를 구분해야 하기 때문이다. 도달성은 "이 코드가 이미 main을
거쳤다"는 사실을 정확히 표현한다.

### 수동 실행은 가드를 통과시킨다

`workflow_dispatch`는 판정 없이 항상 배포한다. **2026-08-27 배포 사고 복구가 정확히 이
경로였다** — 마이그레이션 단계에서 잡이 죽어 `up -d`가 실행되지 않았고, 같은 내용을 수동
실행으로 다시 올려 컨테이너를 교체했다. 그때 `staging`과 `main`이 같았다면 가드가 복구를
막았을 것이다. 수동 실행은 사람의 명시적 의도이므로 자동 판정보다 우선한다.

## 비범위

- **`production-deploy.yml`**: `main` push로만 트리거되고 `main`으로 들어오는 동기화 push가
  없다. 같은 문제가 없으므로 건드리지 않는다
- **브랜치 전략 전환**(트렁크 기반): 장수 `staging`을 없애면 동기화 단계 자체가 사라지지만,
  배포 파이프라인·문서·팀 습관을 한꺼번에 바꾸는 일이라 이번 불편에 비해 크다. 이 마찰이
  반복되면 그때 검토한다

## 작업 분해

1. `.github/workflows/staging-deploy.yml`에 `check` job 추가, `build`에 `needs`/`if` 연결
   (`deploy`는 `needs: build`라 자동으로 함께 skip된다)
2. `AGENTS.md` 브랜치 동기화 규칙에 "이 push는 배포를 돌리지 않는다"와 수동 실행 예외 명시

## 검증 기준

- 워크플로 YAML이 유효하게 파싱되고 job 의존이 `check → build → deploy`로 연결됨
- 동기화 상태(`staging` HEAD == `main` HEAD)에서 판정이 **skip**
- 기능 누적 상태(squash 전 `staging` 커밋)에서 판정이 **배포**
- 다음 릴리스 동기화에서 Actions에 `check`만 돌고 `build`/`deploy`가 skipped로 뜨는지

## 검증 결과

- **YAML·job 의존**: 파싱 성공. `check`(조건 없음) → `build`(`needs: check`,
  `if: needs.check.outputs.should_deploy == 'true'`) → `deploy`(`needs: build`) 확인
- **판정 로직**: 실제 저장소 커밋으로 두 경우를 실증
  - `origin/staging`(= `origin/main`, 동기화 직후 상태) → `--is-ancestor` 참 → **skip** ✅
  - `f94d502`(squash 전 `staging`에만 있던 커밋) → 거짓 → **배포** ✅

## 남는 문제

- **실동작 확인은 다음 릴리스에서**: 판정 로직은 로컬 git으로 실증했지만, GitHub Actions에서
  `check`만 돌고 `build`/`deploy`가 skipped로 뜨는 것은 다음 `main` → `staging` 동기화 때
  확인한다
- **`check` job이 매 push마다 체크아웃한다**: `fetch-depth: 0`이라 전체 히스토리를 받는다.
  저장소가 작아 수 초 수준이고, 건너뛰는 배포에 비하면 훨씬 싸다
- **브랜치 전략의 마찰은 그대로**: 동기화 규칙을 유지하려고 AGENTS.md에 문단을, 워크플로에
  가드를 두게 됐다. 증상을 정확히 막았을 뿐 `staging`이 "항상 main보다 앞서거나 main과
  동일한" 브랜치라는 구조 자체는 남아 있다
