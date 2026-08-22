# 에러 응답 클라이언트 매핑 정비

**상태**: 완료 (2026-08-20)

## 배경

클라이언트가 서버 에러를 `error.code` 기반으로 분기하려 한다. 현재 서버는 에러 카탈로그
(`app/core/errors.py`)가 한 곳에 모여 있고 raw `HTTPException`을 직접 쓰는 곳이 없어 기반은
좋으나, 매핑을 시작하기 전에 정리해야 할 문제가 세 가지 있다.

1. **봉투를 타지 않는 응답이 있다.** 라우트 404/405와 처리되지 않은 예외는
   `success/error/timestamp` 봉투 없이 나간다. 클라가 `error.code`를 무조건 기대하면 파싱이 깨진다.
2. **메시지 언어가 섞여 있다.** 42개 중 16개가 영어다. 또한 도메인 용어가 이탈해 있어
   `PROPOSAL_NOT_FOUND`와 `OFFER_NOT_FOUND`의 메시지가 `"제안을 찾을 수 없습니다."`로 **완전히 동일**하다.
3. **`NOTIFICATION_NOT_FOUND`의 wire code가 `"ERROR"`다.** 의미 없는 값이라 클라가 매핑할 수 없다.

## 결정 사항

| 항목 | 결정 | 근거 |
|---|---|---|
| `details` 타입 | `Optional[str]` 유지. 첫 번째 검증 에러만 `"필드: 메시지"`로 전달 | 필드별 인라인 에러는 현재 요구사항 아님. 계약 변경 없음 |
| 도메인 용어 | proposal = **요청**, offer = **지원** | 알림 문구 개정판(`2026-08-18-notification-copy-revision`)이 이미 이 용어를 쓴다 |
| 토큰 계열 4개 통합 | 유지. `INVALID_TOKEN` 단일 코드 | 강제 로그아웃 판정을 코드가 아닌 엔드포인트로 하면 충분 (아래) |
| 강제 로그아웃 기준 | `POST /v1/auth/refresh`의 **401 `INVALID_TOKEN`** 또는 **404 `USER_NOT_FOUND`** | 그 외 엔드포인트의 `INVALID_TOKEN`은 access 토큰 만료를 포함하므로 로그아웃 트리거로 쓰면 60분마다 전원 로그아웃된다 |
| `OFFER_PROPOSAL_NOT_FOUND` | enum 제거, `PROPOSAL_NOT_FOUND`로 통합 | 용어 통일 후 code·message가 완전히 같아져 별칭 의미가 사라진다 |
| `REQUIRED_TERMS_INVALID` | enum 유지 (code는 `VALIDATION_ERROR`) | 메시지가 달라 유지 가치가 있다 |

## 작업 1 — 응답 봉투를 예외 없이 적용

현재 `app/main.py`는 `HTTPException`과 `RequestValidationError` 두 개만 핸들러를 등록한다.
FastAPI의 `HTTPException`은 Starlette `HTTPException`의 **하위 클래스**라, 상위 클래스로 발생하는
라우트 404/405는 이 핸들러에 걸리지 않는다.

| 상황 | 현재 응답 | 변경 후 |
|---|---|---|
| 없는 경로 | `{"detail":"Not Found"}` (404) | 봉투 + code `NOT_FOUND` |
| 허용되지 않은 메서드 | `{"detail":"Method Not Allowed"}` (405) | 봉투 + code `METHOD_NOT_ALLOWED` |
| 처리되지 않은 예외 | `Internal Server Error` (plain text, 500) | 봉투 + code `INTERNAL_SERVER_ERROR` |

변경 내용:

- `app/core/exceptions.py`에 `starlette_http_exception_handler`, `unhandled_exception_handler` 추가
- `app/main.py`에 `StarletteHTTPException`, `Exception` 핸들러 등록
- `app/core/errors.py`에 `NOT_FOUND`(404), `METHOD_NOT_ALLOWED`(405), `INTERNAL_SERVER_ERROR`(500) 추가
- 500 응답의 `details`는 `settings.app_debug`가 켜진 경우에만 예외 문자열을 담고, 그 외에는 `null`
  (현재 코드는 예외 문자열을 무조건 노출하도록 작성돼 있다 — 프로덕션 정보 노출 방지)
- `unhandled_exception_handler`에서 예외를 `logger.exception`으로 남긴다 (봉투로 감싸면서 스택이 사라지지 않도록)
- `http_exception_handler` 내부의 도달 불가능한 500 fallback 분기 제거.
  같은 함수의 지역변수 `error_detail`이 모듈 임포트 `error_detail`을 가리는 문제도 함께 정리

## 작업 2 — 메시지 한국어화 및 도메인 용어 통일

### 2-1. 영어 → 한국어 (16개)

| code | 현재 | 변경 후 |
|---|---|---|
| `USER_NOT_FOUND` | User not found | 사용자를 찾을 수 없습니다. |
| `VALIDATION_ERROR` (REQUIRED_TERMS_INVALID) | Required terms must be true | 필수 약관에 모두 동의해야 합니다. |
| `INVALID_TOKEN` (INVALID_TOKEN) | Invalid token | 유효하지 않은 토큰입니다. |
| `INVALID_TOKEN` (INVALID_TOKEN_CREDENTIALS) | Could not validate credentials | 인증 정보를 확인할 수 없습니다. |
| `INVALID_TOKEN` (INVALID_TOKEN_TYPE) | Invalid token type | 토큰 종류가 올바르지 않습니다. |
| `INVALID_TOKEN` (MISSING_CREDENTIALS) | Missing credentials | 인증 정보가 없습니다. |
| `INVALID_TOKEN` (INVALID_AUTHENTICATION_CREDENTIALS) | Invalid authentication credentials | 인증 정보가 올바르지 않습니다. |
| `INVALID_CREDENTIALS` | Invalid credentials | 로그인 정보가 올바르지 않습니다. |
| `SMS_SENDER_NOT_CONFIGURED` | SMS sender not configured | SMS 발신 설정이 완료되지 않았습니다. |
| `SMS_SEND_FAILED` | SMS sending failed | 인증번호 발송에 실패했습니다. 잠시 후 다시 시도해주세요. |
| `PHONE_ALREADY_EXISTS` | Phone number already exists | 이미 가입된 휴대폰 번호입니다. |
| `PHONE_VERIFICATION_NOT_FOUND` | Phone verification not found | 인증 요청 내역을 찾을 수 없습니다. |
| `PHONE_VERIFICATION_EXPIRED` | Phone verification expired | 인증번호가 만료되었습니다. 다시 요청해주세요. |
| `PHONE_VERIFICATION_CODE_MISMATCH` | Phone verification code mismatch | 인증번호가 일치하지 않습니다. |
| `PHONE_VERIFICATION_SEND_RATE_LIMITED` | Too many verification requests | 인증번호 요청이 너무 많습니다. 잠시 후 다시 시도해주세요. |
| `NOTIFICATION_NOT_FOUND` | Notification not found | 알림을 찾을 수 없습니다. |

### 2-2. 도메인 용어 교정 (proposal=요청 / offer=지원)

| code | 현재 | 변경 후 |
|---|---|---|
| `PROPOSAL_NOT_FOUND` | 제안을 찾을 수 없습니다. | 요청을 찾을 수 없습니다. |
| `PROPOSAL_NOT_EDITABLE` | 수정할 수 없는 제안 상태입니다. | 수정할 수 없는 요청 상태입니다. |
| `PROPOSAL_NOT_CANCELLABLE` | 취소할 수 없는 제안 상태입니다. | 취소할 수 없는 요청 상태입니다. |
| `PROPOSAL_NOT_OPEN` | 제안을 받을 수 없는 요청 상태입니다. | 지원을 받을 수 없는 요청 상태입니다. |
| `OFFER_NOT_FOUND` | 제안을 찾을 수 없습니다. | 지원 내역을 찾을 수 없습니다. |
| `SELF_OFFER_NOT_ALLOWED` | 오더러는 본인의 요청에 러너로 제안할 수 없습니다. | 본인의 요청에는 지원할 수 없습니다. |
| `DUPLICATE_OFFER` | 이미 해당 요청에 제안을 제출했습니다. | 이미 해당 요청에 지원했습니다. |
| `OFFER_NOT_CANCELLABLE` | 취소할 수 없는 제안 상태입니다. | 취소할 수 없는 지원 상태입니다. |
| `OFFER_NOT_ACCEPTABLE` | 수락할 수 없는 제안 상태입니다. | 수락할 수 없는 지원 상태입니다. |
| `OFFER_NOT_UPDATABLE` | 업데이트할 수 없는 제안 상태입니다. | 변경할 수 없는 지원 상태입니다. |

`OFFER_PROPOSAL_NOT_FOUND`는 위 교정 후 `PROPOSAL_NOT_FOUND`와 완전히 동일해지므로 enum에서 제거하고
호출부(`app/services/offer/offer_service.py`, `app/api/v1/offer/offer_router.py`)를
`PROPOSAL_NOT_FOUND`로 바꾼다. enum 42개 → 41개, wire code는 36개 유지.

## 작업 3 — `NOTIFICATION_NOT_FOUND` wire code 교정

`ApiErrorSpec(404, "ERROR", ...)` → `ApiErrorSpec(404, "NOTIFICATION_NOT_FOUND", ...)`.
`"ERROR"`를 쓰는 유일한 항목이므로 이 변경 후 `"ERROR"` 코드는 완전히 사라진다.

## 작업 4 — 클라이언트 매핑 문서 작성

`docs/api-spec/error-codes.md` 신규 작성. 내용:

- 응답 봉투 구조와 각 필드의 계약 (`code`가 유일한 분기 기준, `message`는 표시용, 파싱 금지)
- **wire code 기준** 전체 표 (36개 + 작업 1에서 추가되는 3개 = 39개). enum 이름이 아닌 실제 나가는 코드 기준
- 인증 실패 처리 규칙 — 강제 로그아웃은 `/v1/auth/refresh`의 `INVALID_TOKEN` / `USER_NOT_FOUND`로만 판정,
  그 외 `INVALID_TOKEN`은 토큰 재발급 시도 신호
- `docs/api-spec/README.md`에서 새 문서로 링크

## 작업 5 — 성공 메시지·Swagger 문구의 용어 통일

'제안'이라는 용어를 코드베이스에서 완전히 제거한다. 다만 현재 '제안'은 **두 가지 다른 대상**을
가리키고 있어 일괄 치환하면 안 된다. proposal을 '제안'이라 부르는 곳은 '요청'으로,
offer를 '제안'이라 부르는 곳은 '지원'으로 각각 바꾼다.

### 5-1. proposal → '요청' (현재 '제안'으로 잘못 표기된 곳)

| 위치 | 현재 | 변경 후 |
|---|---|---|
| `app/core/openapi.py:333` (`PROPOSAL_UPDATE_EXAMPLE`) | 제안이 수정되었습니다. | 요청이 수정되었습니다. |
| `app/core/openapi.py:338` (`PROPOSAL_CANCEL_EXAMPLE`) | 제안이 취소되었습니다. | 요청이 취소되었습니다. |
| `app/api/v1/proposal/proposal_router.py:219` | 제안이 수정되었습니다. | 요청이 수정되었습니다. |
| `app/api/v1/proposal/proposal_router.py:244` | 제안이 취소되었습니다. | 요청이 취소되었습니다. |
| `app/api/v1/admin/admin_router.py:82` | …입금을 확인하여 제안을 POSTED 상태로… | …입금을 확인하여 요청을 POSTED 상태로… |
| `app/api/v1/admin/admin_router.py:121-122` | 입금 대기 중인 제안 목록 조회 | 입금 대기 중인 요청 목록 조회 |

같은 `PROPOSAL_CREATE_EXAMPLE`이 이미 `"요청이 등록되었습니다."`를 쓰고 있어, 수정·취소만 이탈해 있었다.

### 5-2. offer → '지원'

| 위치 | 현재 | 변경 후 |
|---|---|---|
| `app/core/openapi.py:475` (`OFFER_CREATE_EXAMPLE`) | 제안이 제출되었습니다. | 지원이 접수되었습니다. |
| `app/core/openapi.py:511` (`OFFER_ACCEPT_EXAMPLE`) | 제안이 수락되었습니다. | 지원이 수락되었습니다. |
| `app/core/openapi.py:517` (`OFFER_RESOLVED_EXAMPLE`) | 제안 분쟁이 해결되었습니다. | 지원 분쟁이 해결되었습니다. |
| `app/api/v1/offer/offer_router.py:95` | 제안이 제출되었습니다. | 지원이 접수되었습니다. |
| `app/api/v1/offer/offer_router.py:195` | 제안이 수락되었습니다. | 지원이 수락되었습니다. |
| `app/api/v1/admin/admin_router.py:180` | 제안 분쟁이 해결되었습니다. | 지원 분쟁이 해결되었습니다. |

### 5-3. Swagger 태그·summary·description

`app/api/v1/offer/offer_router.py`의 태그 `["제안"]` → `["지원"]`,
그리고 summary·description 14곳의 '제안'을 '지원'으로 교체 (예: "러너 제안 등록" → "러너 지원 등록",
"제안 상세 조회" → "지원 상세 조회"). `app/api/v1/admin/admin_router.py:165-166`의
"제안 분쟁 해결 처리"도 "지원 분쟁 해결 처리"로 바꾼다.
`app/main.py:84`의 API description "심부름 요청, 제안, 미션, 인증" → "심부름 요청, 지원, 미션, 인증".

### 5-4. 테스트 문구 단언 갱신

| 파일 | 대상 |
|---|---|
| `tests/test_openapi.py:125` | `"제안이 수락되었습니다."` → `"지원이 수락되었습니다."` |
| `tests/test_offer_integration.py:69` | `"제안이 제출되었습니다."` → `"지원이 접수되었습니다."` |
| `tests/test_offer_integration.py:418` | `"제안이 수락되었습니다."` → `"지원이 수락되었습니다."` |
| `tests/test_proposal_integration.py:347` | `"제안이 수정되었습니다."` → `"요청이 수정되었습니다."` |
| `tests/test_proposal_integration.py:391` | `"제안이 취소되었습니다."` → `"요청이 취소되었습니다."` |

## 작업 6 — 죽은 알림 디스패처 코드 제거

`app/services/notification/notification_dispatcher.py`의 `notify_*` 메서드 11개를 삭제한다.

- 호출처가 **0개**다. 실사용 알림은 `app/listeners/notification_listener.py`가
  도메인 이벤트(`OfferCreatedEvent` 등)를 받아 처리하며, `app/main.py:41`의
  `notification_listener.register_all()`로 앱 시작 시 등록된다
- 예: 지원 발생 알림의 실제 문구는 리스너의 `"누군가 지원했어요! 👀"`이고,
  디스패처의 `"새로운 제안이 도착했습니다!"`는 도달하지 않는다
- 코드베이스에 남은 '의뢰'·'러너 배정' 등 구 문구가 전부 이 메서드들 안에 있어,
  삭제하면 작업 5의 '제안 제거'가 예외 없이 완결된다

**남기는 것**: `send_custom_notification`. 테스트 알림 발송 엔드포인트
(`app/api/v1/notification/notification_router.py:142`)에서 실제로 쓰인다.
`tests/test_notification_integration.py`의 `RecordingNotificationDispatcher`도
이 메서드만 구현하고 있어 테스트 수정이 필요 없다.

파일은 155줄 → 약 30줄이 된다.

## 범위 밖

- **`details` 배열화** — 필드별 인라인 에러가 필요해지면 별도 계획으로. 클라 계약 변경이라 함께 진행하지 않는다
- **알림 문구** — `app/listeners/notification_listener.py`의 개정판이 이미 '요청/지원' 용어를 쓰고 있어 변경 불필요
- **`NotificationType` 열거형 멤버 정리** — 작업 6 이후 참조가 사라지는 멤버가 생기지만,
  DB `notifications.notification_type` 컬럼에 기존 레코드 값이 남아 있을 수 있어 열거형은 건드리지 않는다
- **access 토큰 만료와 위조의 분리** (`TOKEN_EXPIRED` 신설) — 위 강제 로그아웃 규칙으로 해결되므로 불필요

## 검증

- `pytest tests/test_errors.py tests/test_openapi.py` — 카탈로그 구조와 Swagger 예시 일관성
- `pytest` 전체 — `error["code"]` 단언이 있는 통합 테스트 8개 파일이 영향받는다.
  코드 값은 `NOTIFICATION_NOT_FOUND` 외에는 바뀌지 않으므로 대부분 통과해야 정상
- 봉투 적용 확인용 신규 테스트를 `tests/test_errors.py`에 추가:
  - 없는 경로 요청이 봉투 + `NOT_FOUND` 반환
  - 허용되지 않은 메서드가 봉투 + `METHOD_NOT_ALLOWED` 반환
  - 핸들러에서 예외 발생 시 봉투 + `INTERNAL_SERVER_ERROR` 반환, `app_debug=False`면 `details`가 `null`
- `grep -rn '"ERROR"' app` 결과가 비어 있는지 확인
- `grep -rn '제안\|의뢰' app tests` 결과가 비어 있는지 확인 (작업 5·6 완료 후 예외 없이 0건)
- `pytest tests/test_notification_integration.py` — 디스패처 축소 후에도 테스트 알림 발송이 동작하는지 확인
- 에러 카탈로그 메시지 전체가 한국어인지 확인 (`tests/test_errors.py`에 한글 포함 단언 추가)

## 실행 결과

전 작업 완료. `pytest` 174건 통과.

| 작업 | 결과 |
|---|---|
| 1 | `StarletteHTTPException`·`Exception` 핸들러 등록. 라우트 404/405와 미처리 예외가 봉투를 탄다. 500 `details`는 `APP_DEBUG`에서만 노출 |
| 2 | 영어 메시지 16개 한국어화, 용어 10개 교정, `OFFER_PROPOSAL_NOT_FOUND` 통합 |
| 3 | `NOTIFICATION_NOT_FOUND` wire code 교정. `"ERROR"` 코드 소멸 |
| 4 | `docs/api-spec/error-codes.md` 작성 (wire code 39개), `docs/api-spec/README.md`에서 링크 |
| 5 | 성공 메시지·Swagger 문구 33건 교체. `app`·`tests`에서 '제안'·'의뢰' 0건 |
| 6 | 디스패처 죽은 메서드 11개 제거 (155줄 → 32줄) |

내부 enum은 41개 → 44개가 되었다. `OFFER_PROPOSAL_NOT_FOUND` 1개를 제거하고
작업 1의 공통 코드 3개(`NOT_FOUND`, `METHOD_NOT_ALLOWED`, `INTERNAL_SERVER_ERROR`)를 추가한 결과다.
wire code는 36개 → 39개.

### 후속

- TD-008: 참조가 사라진 `NotificationType` 멤버 정리 (DB 레코드 확인 후)
- 클라이언트: `NOTIFICATION_NOT_FOUND` 코드 변경 반영 필요 (`"ERROR"` → `"NOTIFICATION_NOT_FOUND"`).
  이번 변경에서 클라이언트 계약이 바뀐 유일한 코드다
