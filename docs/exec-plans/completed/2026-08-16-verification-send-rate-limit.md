# 인증번호 재발송 정책 변경

## 목표

인증번호 재발송을 막는 5분 대기 규칙을 제거하고, 같은 휴대폰 번호 기준 **5분당 3회** 발송 제한으로 대체한다. 인증에 성공하면 카운트를 초기화한다.

## 배경

기존 `PhoneVerificationService.send`는 활성 PENDING 레코드가 있으면 409 `PHONE_VERIFICATION_ALREADY_SENT`로 거부했다. 코드 TTL이 5분이므로 SMS가 도착하지 않거나 사용자가 메시지를 지운 경우 **최대 5분을 기다려야 재발송이 가능**해 이탈 요인이 된다.

대기 시간으로 남용을 막는 대신, 재발송을 즉시 허용하되 횟수로 통제한다.

## 범위

- `has_active_pending` 기반 재발송 차단(409)을 제거한다.
- `purpose` + `phone` 기준 최근 5분 내 발송이 3회 이상이면 거부한다.
- 마지막 인증 성공(VERIFIED) 시점 이후의 발송만 카운트한다.
- 재발송 시 이전 PENDING 레코드를 EXPIRED로 무효화해 최신 코드만 유효하게 한다.
- 신규 에러 코드 `PHONE_VERIFICATION_SEND_RATE_LIMITED` (HTTP 429)를 추가하고, 사용처가 사라진 `PHONE_VERIFICATION_ALREADY_SENT`를 제거한다.
- SIGNUP, LOGIN 두 purpose에 동일하게 적용한다.

## 비범위

- IP 기준 rate limit
- Redis 등 외부 저장소 도입 (기존 `auth_phone_verifications` 테이블 조회로 해결)
- 스키마 변경 및 Alembic 마이그레이션 (신규 컬럼 없음)

## 정책 값

| 항목 | 값 |
|---|---|
| 제한 횟수 | 3회 |
| 기준 기간 | 5분 (`VERIFICATION_CODE_TTL`과 동일) |
| 카운트 단위 | `purpose` + `phone` |
| 초기화 조건 | 해당 번호/purpose의 마지막 VERIFIED 이후 발송만 카운트 |
| 재발송 대기 | 없음 (한도 내에서 즉시 가능) |
| 응답 | HTTP 429 `PHONE_VERIFICATION_SEND_RATE_LIMITED` |

## 사용자 흐름

```
0:00  발송   → 200 (1/3)
0:30  재발송 → 200 (2/3), 이전 코드 무효화
1:00  재발송 → 200 (3/3), 이전 코드 무효화
1:10  재발송 → 429 한도 초과
5:00  첫 발송이 기간에서 빠짐 → 다시 발송 가능
```

## 작업 분해

1. `app/services/user_auth/phone_verification.py`에 `VERIFICATION_SEND_MAX_COUNT`, `VERIFICATION_SEND_WINDOW` 정책 상수를 추가한다.
2. `app/core/errors.py`에서 `PHONE_VERIFICATION_ALREADY_SENT`를 제거하고 `PHONE_VERIFICATION_SEND_RATE_LIMITED`(429)를 추가한다.
3. `PhoneVerificationService.send`에서 PENDING 차단을 제거하고, `is_send_rate_limited` 검사와 `expire_pending` 무효화를 넣는다.
4. `app/api/v1/user_auth/auth_router.py`의 응답 예시 에러 코드를 교체한다.
5. 테스트를 갱신한다 (재발송 허용, 한도 초과, 기간 경과, 인증 성공 후 초기화).
6. `docs/api-spec/README.md`, `docs/domains/user-auth/README.md`, `test-scenarios.md`에 정책을 기록한다.

## 검증 전략

- `pytest tests/test_phone_verification.py tests/test_user_auth_integration.py`
- 이전 코드 유효기간 내 재발송이 200이고, 마지막 코드로만 확인되는지 검증
- 3회 연속 발송 후 4번째 요청이 429 + `PHONE_VERIFICATION_SEND_RATE_LIMITED`인지 확인
- 인증 성공 후 재발송이 허용되는지 확인

## 실제 반영 내용

| 파일 | 변경 |
| --- | --- |
| `app/services/user_auth/phone_verification.py` | `VERIFICATION_SEND_MAX_COUNT=3`, `VERIFICATION_SEND_WINDOW=VERIFICATION_CODE_TTL` 추가 |
| `app/services/user_auth/phone_verification_service.py` | `has_active_pending` 제거, `is_send_rate_limited`·`expire_pending` 추가 |
| `app/core/errors.py` | `PHONE_VERIFICATION_ALREADY_SENT` 제거, `PHONE_VERIFICATION_SEND_RATE_LIMITED`(429) 추가 |
| `app/api/v1/user_auth/auth_router.py` | signup/login send 응답 예시 에러 코드 교체 |
| `tests/test_phone_verification.py` | 발송 제한 정책 상수 검증 추가 |
| `tests/test_user_auth_integration.py` | 재발송 허용·한도 초과·기간 경과·성공 후 초기화 케이스 추가, 기존 409 검증을 200으로 수정 |
| `docs/api-spec/README.md` | 에러 표에서 409 제거, 429 추가 |
| `docs/domains/user-auth/README.md`, `test-scenarios.md` | 발송 제한 정책 기록 |

스키마 변경 없음. Alembic 마이그레이션 불필요.

## 검증 근거

- 실행일: 2026-08-16
- 환경: Python 3.12.14, MySQL 8.0 (`docker-compose.test.yml`, 포트 3307)
- 명령: `pytest -q`
- 결과: **162 passed** (auth 관련 46건 포함)
- 확인한 동작: 유효기간 내 재발송 200 및 이전 코드 무효화, 4번째 발송 429, 발송 기록이 기간 밖으로 밀리면 재허용, 인증 성공 후 카운트 초기화

## 남은 리스크와 후속 작업

- **클라이언트 영향**: 409 `PHONE_VERIFICATION_ALREADY_SENT`가 더 이상 발생하지 않는다. 앱이 이 코드를 처리하거나 재발송 버튼을 5분간 비활성화하고 있다면 429 처리로 교체해야 한다. → `tech-debt-tracker.md` TD-006
- **카운트 기준**: 휴대폰 번호 단위이므로 번호를 바꿔가며 반복 요청하는 남용은 막지 못한다. IP 기준 제한은 이번 범위 밖.
- **동시 요청**: 같은 번호로 동시에 여러 요청이 들어오면 카운트 검사와 INSERT 사이 경합으로 한도를 1~2건 초과할 수 있다. SMS 비용 관점에서 허용 가능한 수준으로 판단했다.

## 상태

- [x] 구현
- [x] 테스트 통과 — 전체 162 passed (2026-08-16, 로컬 MySQL 8)
- [x] 문서 반영
- [x] 완료 — `completed/`로 이동
