# 배포 마이그레이션이 락을 무한 대기하지 않게 한다

작성일: 2026-08-28 · 상태: 구현·로컬 검증 완료, staging 재배포 검증 대기

## 배경

2026-08-27 staging 배포(`d745c85`, PR #20)가 `Deploy to EC2` 잡에서 **2시간 11분** 매달린 뒤
실패했다. 로그의 마지막 두 줄이 증상 전부다.

```
INFO  [alembic.runtime.migration] Running upgrade 0033_admin_login_lockout -> 0034_dedupe_fcm_tokens
client_loop: send disconnect: Broken pipe
Error: Process completed with exit code 255.
```

`0034` 시작 로그가 찍힌 뒤 2시간 11분 동안 아무 출력이 없었고, 그 사이 SSH 세션이 죽었다.
`client_loop: send disconnect`는 원인이 아니라 결과다 — 마이그레이션이 멈춰 있었고,
keepalive가 없는 SSH 연결이 그 대기 시간을 견디지 못했다.

## 사후 조사 결과

배포 실패 13시간 뒤 staging DB와 EC2를 조사했다.

| 확인 항목 | 결과 |
| --- | --- |
| `alembic_version` | `0034_dedupe_fcm_tokens` — **마이그레이션은 성공했다** |
| `fcm_token_hash` 컬럼 | `char(64)` / `STORED GENERATED` 정상 생성 |
| `uk_user_fcm_tokens_fcm_token_hash` | `non_unique=0` 유니크 인덱스 정상 생성 |
| 중복 토큰 | 0건 |
| `user_fcm_tokens` 행 수 | **7행** |
| 남은 락 · 열린 트랜잭션 | 없음 (조회 세션 자신뿐) |
| `@@lock_wait_timeout` | **31536000 (365일)** |
| `@@innodb_lock_wait_timeout` | 50 |
| `app-staging-run-*` 좀비 컨테이너 | 없음 |

SSH가 끊긴 뒤에도 `docker compose run` 컨테이너는 EC2에서 계속 돌아 마이그레이션을 끝냈다.
죽은 것은 GitHub Actions 쪽 터미널뿐이었다. **DB는 정상이고 수동 복구는 필요 없다.**

## 원인

행이 **7개뿐인** 테이블이다. [`0034`](../../../alembic/versions/0034_dedupe_fcm_tokens.py)의
self-join DELETE도, 테이블을 복사하는 `ADD COLUMN ... STORED`도 7행에서는 밀리초 단위로 끝난다.
2시간 11분은 작업 시간이 아니라 **대기 시간**이다.

`@@lock_wait_timeout`이 MySQL 기본값인 **365일**이다. 그래서 메타데이터 락(MDL)을 기다리는
DDL은 에러를 내지 않고 사실상 영원히 멈춰 있는다. `innodb_lock_wait_timeout`(50초)은 InnoDB의
행 락에만 적용되고 MDL에는 적용되지 않아 이 상황을 구제하지 못한다.

락을 쥔 쪽은 구 `orderrun-app-staging`이다. [`deploy.sh:88-90`](../../../scripts/deploy.sh)은
**구 앱이 그대로 떠 있는 상태에서** 마이그레이션을 먼저 돌린다 — 새 이미지가 아직 없는 컬럼을
읽어 요청이 실패하는 구간을 없애려는 의도적 순서이고, 이 순서 자체는 옳다. 다만 그 결과로
DDL과 라이브 트래픽이 같은 테이블에서 만나고, 앱 커넥션이 MDL을 쥐고 있으면 DDL이 무한정
기다린다. 락을 쥔 세션은 조사 시점에 이미 사라져 어떤 쿼리였는지까지는 특정할 수 없다.

즉 이번 실패는 `0034`의 버그가 아니다. **DDL을 포함한 모든 마이그레이션이 같은 방식으로
배포를 무한정 막을 수 있는 구조적 문제**이고, 다음 DDL 마이그레이션에서 그대로 재현된다.

## 부수 피해

마이그레이션 단계에서 잡이 죽어 그다음 `docker compose up -d`가 실행되지 않았다. 그 결과
**staging은 13시간 동안 구 이미지로 돌았다.**

```
컨테이너가 쓰는 이미지 : sha256:09c55cef...
:staging 태그가 가리키는 이미지 : sha256:f955db6d...
```

`pull`은 마이그레이션 **전에** 끝나 로컬 태그는 갱신됐지만 컨테이너는 교체되지 않았다.
게다가 구 코드는 새로 생긴 유니크 제약을 모르는 채로 돌았다.

## 범위

세 겹으로 막는다. 어느 하나가 뚫려도 다음 겹에서 잡히게 한다.

1. **`alembic/env.py`** — 마이그레이션 세션의 `lock_wait_timeout`을 짧게 설정. 365일 무한
   대기 대신 명확한 에러로 실패시킨다. **가장 근본적인 수정**
2. **`scripts/deploy.sh`** — `alembic upgrade head`를 `timeout`으로 감싼다. env.py가 못 잡는
   대기(DB 커넥션 자체가 안 열리는 경우 등)까지 잡는다
3. **배포 워크플로 2종** — SSH keepalive로 broken pipe를 막아 **실패 원인 로그를 잃지 않게**
   하고, deploy 잡에 `timeout-minutes`를 걸어 러너가 몇 시간씩 매달리지 않게 한다

## 비범위

- **마이그레이션 실행 순서 변경**: 구 앱을 먼저 내리고 마이그레이션하는 방식은 다운타임을
  만든다. 현재 순서(마이그레이션 먼저)가 무중단 배포에 맞고, 실패 시 구 앱을 그대로 두는
  것도 의도된 설계다. 그대로 둔다
- **온라인 DDL 도구 도입**(gh-ost, pt-online-schema-change): 테이블 규모가 수천 행 수준이라
  도구 도입 비용이 이득보다 크다
- **`0034` 마이그레이션 수정**: 이미 적용됐고 결과도 정상이다. 롤백·재작성하지 않는다
- **배포 실패 알림**: 별도 관심사다. 필요해지면 tech-debt로 기록한다

## 설계 결정

### 왜 `innodb_lock_wait_timeout`은 안 건드리는가

이미 50초로 합리적인 값이고, 이번 사고와 무관하다. MDL 대기는 `lock_wait_timeout`이 지배한다.
둘을 함께 만지면 무엇이 무엇을 고쳤는지 알 수 없어진다.

### 타임아웃 값

| 값 | 설정 | 근거 |
| --- | --- | --- |
| `lock_wait_timeout` | **60초** | 락을 60초 쥐고 있는 요청은 이 서비스에 없다. 60초를 넘겼으면 정상 상황이 아니므로 배포를 세우는 편이 낫다 |
| 마이그레이션 전체 | **600초** | 지금까지 마이그레이션은 모두 수 초 내에 끝났다. 10분이면 향후 데이터 백필이 있어도 충분하고, 2시간과는 자릿수가 다르다 |
| deploy 잡 | **20분** | 마이그레이션 10분 + pull·기동·헬스체크 여유 |

`lock_wait_timeout`은 **락 획득 대기**만 제한한다. 락을 잡은 뒤 실제 DDL이 오래 걸리는 것은
제한하지 않으므로, 대형 ALTER를 중간에 자를 위험은 없다.

두 값 모두 환경변수로 덮을 수 있게 한다. 예상 못 한 대형 마이그레이션에서 코드 수정 없이
한 번만 늘려 돌릴 수 있어야 한다.

### 왜 SSH keepalive가 타임아웃보다 덜 중요한가

keepalive는 무한 대기 자체를 막지 못한다. 다만 이번처럼 **연결이 먼저 죽으면 진짜 실패
사유가 로그에 안 남는다.** 위 두 타임아웃이 남길 에러 메시지를 실제로 받아 보기 위한
보조 장치다.

## 작업 분해

1. `alembic/env.py`
   - `MIGRATION_LOCK_WAIT_TIMEOUT_SECONDS` 환경변수(기본 60) 파싱
   - `run_migrations_online`에서 `context.configure` 전에 세션 변수 설정
   - MySQL 방언일 때만 실행 (다른 방언에는 없는 변수라 오류)
   - offline 모드는 커넥션이 없으므로 대상 아님
2. `scripts/deploy.sh`
   - `MIGRATION_TIMEOUT_SECONDS`(기본 600)로 `alembic upgrade head`를 `timeout` 래핑
   - 종료 코드 124(타임아웃)를 구분해, 무엇을 확인해야 하는지 알려주는 에러 메시지 출력
3. `.github/workflows/staging-deploy.yml`, `production-deploy.yml`
   - 모든 `ssh`/`scp`에 `-o ServerAliveInterval=30 -o ServerAliveCountMax=6`
   - deploy 잡에 `timeout-minutes: 20`
4. `docs/exec-plans/tech-debt-tracker.md`에 남는 문제 기록

## 검증 기준

- `pytest -q`에 회귀 없음 (TD-010의 기존 1건 실패 외 신규 실패 없음)
- 로컬 MySQL에서 `alembic upgrade head`가 정상 동작하고, 로그에 세션 타임아웃 설정이 반영됨
- 로컬에서 **락 경합을 인위적으로 재현**했을 때 마이그레이션이 60초 안에 실패하고,
  365일 대기하지 않음 — 다른 세션에서 `user_fcm_tokens`에 트랜잭션을 열어 두고
  DDL 마이그레이션을 돌려 확인
- `bash -n scripts/deploy.sh` 구문 통과
- 두 워크플로 YAML이 유효하게 파싱됨
- staging 재배포가 정상 완료되고 `orderrun-app-staging`이 새 이미지로 교체됨

## 실제 반영 내용

| 파일 | 변경 |
| --- | --- |
| `alembic/env.py` | `MIGRATION_LOCK_WAIT_TIMEOUT_SECONDS`(기본 60) 추가. MySQL일 때 `connect` 이벤트에서 DBAPI 커서로 `SET SESSION lock_wait_timeout` 실행 |
| `scripts/deploy.sh` | `MIGRATION_TIMEOUT_SECONDS`(기본 600)로 `alembic upgrade head`를 `timeout` 래핑. 종료 코드 124/137(타임아웃)과 그 외 실패를 구분해 다른 안내 메시지 출력 |
| `.github/workflows/staging-deploy.yml` | `Setup SSH key`에서 `~/.ssh/config`에 `ServerAliveInterval 30` / `ServerAliveCountMax 6` 기록(ssh·scp 모두 적용), deploy 잡에 `timeout-minutes: 20` |
| `.github/workflows/production-deploy.yml` | 위와 동일 |

### 구현 중 발견한 함정: `exec_driver_sql`이 마이그레이션 커밋을 삼킨다

처음에는 `connectable.connect()` 직후 `connection.exec_driver_sql("SET SESSION ...")`로 구현했다.
**이 구현은 마이그레이션 결과를 커밋하지 않는 심각한 회귀였다.** SQLAlchemy 2.x에서
`Connection.exec_driver_sql()`은 암묵적 트랜잭션을 시작하고, 그 위에 alembic의
`context.begin_transaction()`이 중첩되면서 `alembic_version` UPDATE가 유실된다.

증상이 조용해서 위험하다 — 마이그레이션 DDL은 (MySQL의 implicit commit 때문에) 적용되는데
`alembic_version`만 갱신되지 않는다. 로컬 검증에서 "34개 마이그레이션이 실행됐는데 버전은
0031"이라는 형태로 드러났고, `general_log`로 `UPDATE alembic_version ...`이 나갔는데도
값이 안 바뀌는 것을 확인해 특정했다.

`connect` 이벤트에서 **DBAPI 커서로 직접** 실행하도록 바꿔 해결했다. 커넥션이 열리는 시점의
드라이버 레벨 작업이라 SQLAlchemy·alembic의 트랜잭션 관리에 관여하지 않는다.

### 검증 결과

로컬 brew MySQL 9.7.1, 별도 DB `orderrun_mig`에서 검증한 뒤 drop했다.

- **세션 변수가 실제로 걸린다**: `general_log`를 켜고 alembic을 실행해
  `SET SESSION lock_wait_timeout = 60`이 나가는 것을 확인
- **커밋 회귀 없음**: `alembic stamp`/`upgrade`가 `alembic_version`을 정상 갱신하는 것을
  수정 전 원본(`git stash`)과 대조해 확인
- **락 경합 시 빠르게 실패한다**: 다른 세션에서 `user_fcm_tokens`에 트랜잭션을 열어 MDL을
  쥔 상태로 `0034`를 실행 → **62초**만에
  `(1205, 'Lock wait timeout exceeded; try restarting transaction')`로 실패.
  수정 전이라면 365일 대기했을 지점이다
- **정상 경로 무영향**: 락이 없으면 `0034`가 그대로 적용되고 `fcm_token_hash` 컬럼과
  유니크 제약이 정상 생성됨
- **`deploy.sh` 분기**: `bash -n` 통과. 타임아웃(124)·일반 실패(1)·성공 세 경로를 분리
  시뮬레이션해 각각 의도한 메시지와 종료 코드를 내는 것 확인.
  (`timeout`은 macOS 기본에 없어 로컬 전체 실행은 불가. EC2 Ubuntu의 coreutils에는 포함)
- **워크플로 YAML**: 두 파일 모두 파싱 성공, heredoc이 의도대로 렌더링되고
  `timeout-minutes: 20` 적용 확인
- **`pytest -q`**: 352 passed, 1 failed — 실패는 TD-010에 기록된 기존
  `test_create_proposal_validation_errors` 1건으로 이번 변경과 무관. 신규 회귀 없음

### 남은 검증 (배포 시)

- staging 재배포에서 `Running database migrations...` 다음이 즉시 통과하는지
  (`0034`가 이미 head라 no-op이어야 한다)
- `orderrun-app-staging`이 새 이미지로 교체되는지 — 사고 당시 컨테이너는 `sha256:09c55cef...`,
  `:staging` 태그는 `sha256:f955db6d...`로 갈라져 있었다

## 남는 문제

- **락을 쥔 범인을 못 잡았다**: 이 계획은 무한 대기를 막을 뿐, 구 앱의 어떤 커넥션이 MDL을
  오래 쥐는지는 밝히지 못한다. 타임아웃이 걸리면 이제 에러가 나므로, 다음에 재현되면
  그때 `performance_schema.metadata_locks`로 추적한다
- **타임아웃은 배포를 실패시킨다**: 락 경합이 잦아지면 배포가 반복 실패할 수 있다. 그때는
  무한 대기로 되돌리는 게 아니라 배포 중 트래픽 차단이나 온라인 DDL 도구를 검토한다
- **`timeout`이 죽인 뒤 컨테이너가 남을 수 있다**: `docker compose run --rm`이 SIGTERM에
  정리를 시도하지만 보장은 아니다. 다음 배포의 `--remove-orphans`가 대부분 회수한다
