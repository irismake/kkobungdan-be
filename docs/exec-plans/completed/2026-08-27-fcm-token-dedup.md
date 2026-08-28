# FCM 토큰 중복 등록 정리

## 목표

한 기기 토큰이 여러 유저 계정에 동시에 남아 다른 계정 앞 알림이 내 기기로 오는 문제를 막는다. 완료 처리 푸시는 오는데 `GET /v1/notifications` 히스토리에는 없다는 증상의 근본 원인.

## 배경

staging DB `user_fcm_tokens`를 조회한 결과 같은 `fcm_token`을 여러 `user_id`가 물고 있는 행이 다수 발견됐다 (데모 로그인 계정 `00000000-0000-4000-8000-000000000000` 포함).

원인은 두 가지가 겹쳐서 발생한다.

1. [`UserProfileService.upsert_fcm_token`](../../../app/services/user_auth/user_profile_service.py)이 로그인한 유저 자신의 row만 갱신하고, 같은 토큰을 들고 있는 다른 유저의 row는 그대로 둔다. 한 기기에서 계정을 바꿔가며 로그인하면 토큰이 여러 유저에게 중복으로 남는다.
2. `user_fcm_tokens.fcm_token`에 유니크 제약이 없어 DB가 중복을 막지 못한다. `user_id`에만 unique가 걸려 있다 ([`models/user.py:124`](../../../app/models/user.py)).

[`NotificationWorker._get_token`](../../../app/services/notification_worker.py)이 `notif.user_id`로 토큰을 조회해 FCM에 발송하므로, 알림 레코드 자체는 정상 유저 앞으로 생성되고 히스토리에도 정상적으로 뜬다. 다만 그 유저 row의 토큰이 실제로는 다른 사람 기기를 가리켜, 알림을 받은 사람과 히스토리를 보는 사람이 어긋난다.

부가로 로그아웃([`auth_router.py:189-195`](../../../app/api/v1/user_auth/auth_router.py))이 사실상 no-op이라 토큰 정리 기회가 하나 더 빠져 있다.

## 범위

- 토큰 upsert 시 같은 토큰을 쥔 다른 유저 row 삭제
- `user_fcm_tokens`에 토큰 유니크 제약 추가 (해시 컬럼 + unique 인덱스, 마이그레이션에서 기존 중복 정리 선행)
- 로그아웃 시 현재 유저의 토큰 row 삭제
- FCM이 `UNREGISTERED` / `SENDER_ID_MISMATCH`를 반환하면 워커가 해당 토큰 row를 정리

## 비범위

- 기기당 다중 토큰 지원 (현재도 유저당 1개 토큰 모델 유지)
- `AuthLogoutRequest`에 `fcm_token` 필드 추가해 기기 단위로 구분하는 것 (지금은 유저당 토큰이 1개라 불필요)
- FCM 재시도 정책 전반 개편 (TD-008/TD-011과 별개)

## 설계 결정: 유니크 제약 방식

`fcm_token`은 `VARCHAR(4096)`이라 그대로 유니크 인덱스를 걸 수 없다 (utf8mb4 기준 최대 인덱스 길이 초과). prefix 인덱스는 앞부분이 같고 뒷부분만 다른 토큰이 있으면 진짜 중복을 놓칠 수 있어 채택하지 않는다.

대신 `fcm_token_hash CHAR(64) AS (SHA2(fcm_token, 256)) STORED` 생성 컬럼을 추가하고 여기에 unique 인덱스를 건다. 애플리케이션 코드는 이 컬럼을 직접 쓰지 않는다 — DB가 SHA-256으로 자동 계산해 채운다.

## 작업 분해

1. `alembic/versions/0034_dedupe_fcm_tokens.py`
   - 토큰별로 가장 최근 `updated_at`(동률이면 큰 `id`) 1건만 남기고 나머지 삭제
   - `fcm_token_hash CHAR(64) AS (SHA2(fcm_token, 256)) STORED NOT NULL` 컬럼 추가
   - `uk_user_fcm_tokens_fcm_token_hash` unique 인덱스 추가
   - downgrade: 인덱스·컬럼 제거 (삭제된 중복 행은 복구하지 않음, 명시)
2. `UserProfileService.upsert_fcm_token`
   - 같은 토큰을 가진 다른 유저 row를 먼저 삭제한 뒤 upsert
   - `db.commit()`은 호출자(3곳)가 소유하므로 여기서는 커밋하지 않는다. 동시 요청 경합으로 unique 제약에 걸리는 경우는 실제 기기 토큰 충돌 가능성이 사실상 0이라 별도 재시도 없이 호출자의 기존 `except Exception` 처리(rollback 후 에러 응답)에 맡긴다
3. `UserAuthService`의 로그인 시 upsert 경로 2곳은 변경 없음 (같은 `upsert_fcm_token`을 호출하므로 자동으로 반영됨)
4. 로그아웃 엔드포인트: `current_user.id`의 `UserFCMToken` row 삭제 후 커밋
5. `NotificationWorker._send_batch`: 발송 결과 `error_code`가 `UNREGISTERED` 또는 `SENDER_ID_MISMATCH`면 해당 `UserFCMToken` row 삭제
6. 테스트
   - `upsert_fcm_token`이 다른 유저의 동일 토큰 row를 삭제하는지
   - 로그아웃이 토큰 row를 삭제하는지
   - 워커가 `UNREGISTERED` 응답을 받으면 토큰 row를 삭제하는지
   - 마이그레이션 upgrade가 기존 중복 데이터를 정리하고 unique 인덱스를 만드는지 (별도 DB로 검증)
7. `docs/generated/db-schema.md` 갱신

## 검증 전략

- `pytest -q` 전체 통과
- 별도 DB(`DB_NAME=orderrun_mig`)에 중복 토큰 fixture를 넣고 `alembic upgrade head` 실행 → 중복 제거 + unique 인덱스 생성 확인 후 DB drop
- staging에서 실제 중복 row 개수를 배포 전후로 비교

## 실제 반영 내용

| 파일 | 변경 |
| --- | --- |
| `app/models/user.py` | `UserFCMToken`에 `fcm_token_hash CHAR(64)` 생성 컬럼(`SHA2(fcm_token, 256)` STORED)과 `uk_user_fcm_tokens_fcm_token_hash` unique 제약 추가 |
| `app/services/user_auth/user_profile_service.py` | `upsert_fcm_token`이 upsert 전에 같은 토큰을 쥔 다른 유저 row를 삭제 |
| `app/services/user_auth/user_auth_service.py` | `logout` 메서드 추가 — 현재 유저의 `UserFCMToken` row 삭제·커밋 |
| `app/api/v1/user_auth/auth_router.py` | `/auth/logout`이 `UserAuthService.logout` 호출하도록 변경 (기존엔 no-op) |
| `app/services/notification_worker.py` | FCM이 `UNREGISTERED`/`SENDER_ID_MISMATCH`를 반환하면 해당 유저의 토큰 row 삭제 |
| `alembic/versions/0034_dedupe_fcm_tokens.py` | 토큰별 최신 1건만 남기고 기존 중복 정리, `fcm_token_hash` 컬럼과 unique 제약 추가 (downgrade는 컬럼·제약만 되돌리고 삭제된 중복 행은 복구하지 않음) |
| `tests/test_user_auth_integration.py` | 로그아웃 시 토큰 삭제 검증 추가, 다른 유저가 쥐고 있던 토큰을 새 로그인이 가로채는 테스트 추가, `UserFCMToken` 모델 스펙 테스트에 해시 컬럼·제약 검증 추가 |
| `tests/test_notification_integration.py` | 워커가 `UNREGISTERED` 응답을 받으면 토큰 row를 삭제하는 테스트 추가 |

### 검증 결과

- `pytest -q` 전체: 350 passed, 1 failed (`test_create_proposal_validation_errors` — TD-010에 기록된 기존 실패, 이번 변경과 무관) — 이번 변경으로 새로 깨진 테스트 없음
- 별도 DB(`orderrun_mig`)에서 `0033`까지 올린 뒤 `fcm_token_hash`/unique 제약을 수동으로 제거해 "고치기 전" 상태를 재현하고 중복 토큰 3건(그중 2건 진짜 중복)을 넣은 뒤 `alembic upgrade head` 실행 → 오래된 중복 1건 삭제, 나머지 2건에 해시 컬럼·값이 정상 채워지고 unique 인덱스 생성 확인. `alembic downgrade`로 컬럼·제약이 깨끗이 제거되는 것도 확인 후 DB drop
- `docs/generated/db-schema.md`는 이번 변경으로 갱신할 내용 없음 확인 (테이블 목록은 이미 `user_fcm_tokens`를 O(ORM 매핑)로 기록하고 있고, 컬럼 단위 상세는 이 문서도 `docs/domains/user-auth/README.md`도 원래 다루지 않음)

### 후속 필요 작업 (staging/운영 배포 시)

- `alembic upgrade head` 실행 전 staging DB의 기존 중복 행 수를 한 번 더 확인해 둘 것 (이번 조사에서 발견한 3개 토큰 그룹, 데모 로그인 계정 포함)
- 배포 후 `SELECT COUNT(*) FROM user_fcm_tokens GROUP BY fcm_token HAVING COUNT(*) > 1;`이 0행인지 재확인
