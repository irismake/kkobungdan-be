# `/v1/auth/login/send` 미가입 번호 응답을 USER_NOT_FOUND로 변경

**상태**: 완료 (2026-08-20)

## 배경

클라이언트가 토큰 재발급·강제 로그아웃을 **HTTP 401 상태코드**로 분기하고 있다는 보고가 들어왔다.
`2026-08-20-error-code-client-mapping`에서 정한 계약은 "분기의 유일한 기준은 `error.code`"이고,
강제 로그아웃 판정은 `(엔드포인트, code)` 쌍이다. 상태코드 기반 분기의 실제 결함은 두 가지다.

1. `POST /v1/auth/refresh`의 실패에는 401 `INVALID_TOKEN` 외에 **404 `USER_NOT_FOUND`**(탈퇴 계정)가 있다.
   401만 보는 클라이언트는 이 응답을 흘려보내고, 탈퇴 계정이 재발급을 무한 재시도한다.
2. 401을 내는 코드가 두 종류였다. `INVALID_TOKEN`(갱신하면 회복 가능)과
   `INVALID_CREDENTIALS`(`/v1/auth/login/send`의 미가입 번호, 갱신과 무관).
   전역 인터셉터가 후자를 삼키면 "가입되지 않은 번호" 안내 대신 세션 만료 처리가 뜬다.

클라이언트 수정은 클라이언트대로 필요하지만, 서버 쪽에도 고칠 지점이 있다.
`INVALID_CREDENTIALS`는 **의미상 인증 실패가 아니다.** 토큰을 싣지 않는 비인증 엔드포인트에서
"그 번호로 가입된 계정이 없다"를 말하는 코드이므로 401이 아니라 404 `USER_NOT_FOUND`가 맞다.

## 결정 사항

| 항목 | 결정 | 근거 |
|---|---|---|
| `/v1/auth/login/send` 미가입 번호 | 401 `INVALID_CREDENTIALS` → **404 `USER_NOT_FOUND`** | 인증 실패가 아니라 대상 리소스 부재. `/v1/auth/refresh`의 탈퇴 계정 처리와 같은 의미 |
| `INVALID_CREDENTIALS` 코드 | **카탈로그에서 제거** (wire code 38 → 37) | 유일한 발생 경로가 사라진다. `tests/test_openapi.py`가 고아 코드를 실패로 잡는다. `SMS_SEND_FAILED` 폐기와 같은 처리 |
| 문구 | 공용 문구 대신 로그인 전용 `AppError.PHONE_NOT_REGISTERED` 추가 | "사용자를 찾을 수 없습니다."는 로그인 화면 문구로 어색하다. `INVALID_TOKEN`이 사유 5종을 한 코드로 묶는 기존 패턴과 동일 |
| 계정 존재 여부 노출 | 현행 유지 | 미가입일 때 에러를 내는 시점에 이미 노출된다. 상태코드만 바뀌므로 노출 범위 변화 없음 |

부수 효과: **401로 나가는 wire code가 `INVALID_TOKEN` 하나만 남는다.**
클라이언트가 상태코드로 분기하더라도 오판할 여지가 구조적으로 사라진다.
계약은 여전히 `error.code` 기준이지만, 잘못 구현했을 때의 폭발 반경이 줄어든다.

## 작업

- `app/core/errors.py`
  - `ErrorCode.INVALID_CREDENTIALS`, `AppError.INVALID_CREDENTIALS`, `ERRORS` 항목 제거
  - `AppError.PHONE_NOT_REGISTERED` 추가 → 404 `USER_NOT_FOUND`,
    `"가입되지 않은 휴대폰 번호입니다. 회원가입 후 이용해주세요."`
- `app/services/user_auth/user_auth_service.py` — `send_login_verification`이 `PHONE_NOT_REGISTERED`를 던진다
- `app/api/v1/user_auth/auth_router.py` — `/login/send`의 `error_responses`를 교체
- `docs/api-spec/error-codes.md` — 표에서 `INVALID_CREDENTIALS` 삭제, 개수(38/39 → 37/38) 갱신,
  401 단일 코드 사실을 인증 실패 처리 절에 명시
- `docs/api-spec/README.md`, `docs/product-specs/error-copy-policy.md` — 같은 정리
- `tests/test_user_auth_integration.py` — 미가입 번호 로그인 발송이 404 `USER_NOT_FOUND`임을 검증

## 검증 (2026-08-20)

- `pytest` 전체 183건 통과. 새 회귀 테스트
  `test_login_send_on_unregistered_phone_returns_user_not_found`가 404 `USER_NOT_FOUND`와 문구,
  그리고 인증 레코드가 남지 않는 것을 확인한다
- `test_every_catalog_error_code_appears_in_openapi`가 카탈로그-문서 정합을 보증한다 (고아 코드 없음)
- `openapi.json`에서 401 응답에 등장하는 code는 `INVALID_TOKEN` 하나뿐임을 확인
- `/v1/auth/login/send`의 문서화된 상태는 200/400/404/429/500

## 남은 부채

- `docs/api-spec/README.md`의 에러 코드 표에 카탈로그에 없는 값이 남아 있다
  (`INVALID_REQUEST_PARAMETER`, `EXPIRED_TOKEN`, `PROPOSAL_MEETING_AT_INVALID`,
  `PROPOSAL_ITEM_PRICE_INVALID`, `PROPOSAL_DEPOSIT_INVALID`).
  이번 작업에서는 `INVALID_CREDENTIALS` 행만 제거했다. 정본은 `error-codes.md`이므로
  README 표는 정본을 가리키는 링크로 대체하는 편이 낫다
- 클라이언트의 401 기반 분기 자체는 서버에서 고칠 수 없다. 위 "클라이언트 영향" 공유 필요

## 클라이언트 영향

깨지는 변경이다. 배포 전 클라이언트에 공유해야 한다.

| 대상 | 변경 전 | 변경 후 |
|---|---|---|
| `/v1/auth/login/send` 미가입 번호 | 401 `INVALID_CREDENTIALS` | 404 `USER_NOT_FOUND` |

`INVALID_CREDENTIALS`를 매핑해 둔 클라이언트는 해당 분기를 제거하고,
`/v1/auth/login/send`의 404 `USER_NOT_FOUND`를 회원가입 유도 안내로 처리한다.
`/v1/auth/refresh`의 404 `USER_NOT_FOUND`는 강제 로그아웃이므로 **엔드포인트별로 다르게 처리**해야 한다.
