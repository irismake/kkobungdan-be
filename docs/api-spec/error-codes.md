# 에러 코드 (클라이언트 매핑 정본)

이 문서는 클라이언트가 서버 에러를 분기할 때 쓰는 정본이다.
값의 출처는 `app/core/errors.py`의 `AppError` 카탈로그이며, 코드를 바꾸면 이 표도 함께 갱신한다.

## 응답 봉투

모든 실패 응답은 예외 없이 아래 형태로 나간다. 라우트 404·405와 서버 내부 오류도 포함한다.

```json
{
  "success": false,
  "error": {
    "code": "PROPOSAL_NOT_FOUND",
    "message": "요청을 찾을 수 없습니다.",
    "details": null
  },
  "timestamp": "2026-06-01T12:00:00+09:00"
}
```

| 필드 | 계약 |
|---|---|
| `error.code` | **클라이언트가 분기하는 유일한 기준.** 아래 표의 값만 나간다 |
| `error.message` | 사용자에게 그대로 노출 가능한 한국어 문구. **분기 조건으로 쓰지 말 것** — 문구는 예고 없이 바뀐다 |
| `error.details` | 대부분 `null`. 검증 실패 시에만 `"필드명: 사유"` 문자열이 담긴다 |
| `timestamp` | 에러 발생 시각 (UTC ISO-8601) |

`details`는 항상 문자열이거나 `null`이다. 검증 에러가 여러 개여도 **첫 번째 하나만** 담기므로,
필드별 인라인 에러 표시에는 쓸 수 없다.

## 인증 실패 처리 — 강제 로그아웃 기준

`INVALID_TOKEN`은 액세스 토큰 **만료**를 포함한 5가지 상황에서 나간다.
따라서 **코드만 보고 강제 로그아웃하면 안 된다.** 토큰이 60분마다 만료되므로 전 사용자가 주기적으로 튕긴다.

판단 기준은 코드가 아니라 **어느 엔드포인트에서 실패했는가**이다.

```
401 INVALID_TOKEN 수신
  ├─ POST /v1/auth/refresh 의 응답이었나?
  │     → 강제 로그아웃 (재발급 수단이 죽었으므로 복구 불가)
  └─ 그 외 엔드포인트였나?
        → /v1/auth/refresh 1회 시도
             ├─ 성공 → 새 액세스 토큰으로 원래 요청 재시도
             └─ 실패 → 강제 로그아웃
```

| `/v1/auth/refresh` 응답 | 처리 |
|---|---|
| 401 `INVALID_TOKEN` | 강제 로그아웃 |
| 404 `USER_NOT_FOUND` | 강제 로그아웃 (탈퇴 처리된 계정) |

`USER_NOT_FOUND`를 빠뜨리면 탈퇴한 계정이 로그아웃되지 않은 채 재발급을 계속 시도한다.
401만 인증 실패로 취급하는 클라이언트가 실제로 이 케이스를 놓친다.

**상태코드로 분기하지 말 것.** 401로 나가는 코드가 현재 `INVALID_TOKEN` 하나뿐인 것은 사실이지만,
그건 카탈로그의 현재 상태일 뿐 계약이 아니다. 401에 코드가 추가되면 상태코드로 분기하는 클라이언트는
수정 없이 조용히 오작동한다. 반대로 `USER_NOT_FOUND`는 **엔드포인트에 따라 의미가 다르다** —
`/v1/auth/refresh`에서는 탈퇴 계정(강제 로그아웃)이고, `/v1/auth/login/send`에서는
가입되지 않은 번호(회원가입 안내)다. 세션을 건드려서는 안 된다.

`POST /v1/auth/logout`은 서버에서 토큰을 무효화하지 않는다. 강제 로그아웃은 클라이언트 로컬 상태 정리다.

## 전체 코드 표

| HTTP | code | message | 비고 |
|---|---|---|---|
| 400 | `INVALID_DATE_TIME_FORMAT` | deadline 형식이 올바르지 않습니다. | |
| 400 | `INVALID_STATUS` | 입금 확인 대기 상태가 아닙니다. | |
| 400 | `PHONE_VERIFICATION_CODE_MISMATCH` | 인증번호가 일치하지 않습니다. | |
| 400 | `PHONE_VERIFICATION_EXPIRED` | 인증번호가 만료되었습니다. 다시 요청해주세요. | |
| 400 | `PROPOSAL_DEADLINE_INVALID` | 마감 시각은 현재 시각보다 이후여야 합니다. | |
| 400 | `PROPOSAL_ERRAND_FEE_INVALID` | 심부름비는 1000원 이상이어야 합니다. | |
| 400 | `SELF_OFFER_NOT_ALLOWED` | 본인의 요청에는 지원할 수 없습니다. | |
| 400 | `VALIDATION_ERROR` | 요청 값이 올바르지 않습니다.<br>필수 약관에 모두 동의해야 합니다. | 내부 사유 2종이 같은 코드로 나간다 |
| 401 | `INVALID_TOKEN` | 유효하지 않은 토큰입니다.<br>인증 정보를 확인할 수 없습니다.<br>토큰 종류가 올바르지 않습니다.<br>인증 정보가 없습니다.<br>인증 정보가 올바르지 않습니다. | 내부 사유 5종이 같은 코드로 나간다 |
| 403 | `FORBIDDEN` | 권한이 없습니다. | |
| 403 | `PROPOSAL_SELF_REPORT_NOT_ALLOWED` | 본인의 요청은 신고할 수 없습니다. | |
| 404 | `CHAT_ROOM_NOT_FOUND` | 채팅방을 찾을 수 없습니다. | |
| 404 | `OUTBOX_DELIVERY_NOT_FOUND` | 전달 기록을 찾을 수 없습니다. | 관리자 웹 전용 |
| 404 | `DISPUTE_EVIDENCE_NOT_FOUND` | 분쟁 증빙을 찾을 수 없습니다. | |
| 404 | `MISSION_NOT_FOUND` | 임무를 찾을 수 없습니다. | 관리자 웹 전용 |
| 404 | `NOTIFICATION_NOT_FOUND` | 알림을 찾을 수 없습니다. | |
| 404 | `NOT_FOUND` | 요청하신 경로를 찾을 수 없습니다. | |
| 404 | `OFFER_NOT_FOUND` | 지원 내역을 찾을 수 없습니다. | |
| 404 | `PHONE_VERIFICATION_NOT_FOUND` | 인증 요청 내역을 찾을 수 없습니다. | |
| 404 | `PROPOSAL_NOT_FOUND` | 요청을 찾을 수 없습니다. | |
| 404 | `PROPOSAL_REPORT_NOT_FOUND` | 신고 내역을 찾을 수 없습니다. | |
| 404 | `USER_NOT_FOUND` | 사용자를 찾을 수 없습니다.<br>가입되지 않은 휴대폰 번호입니다. 회원가입 후 이용해주세요. | 내부 사유 2종이 같은 코드로 나간다 |
| 405 | `METHOD_NOT_ALLOWED` | 허용되지 않은 요청 방식입니다. | |
| 409 | `DUPLICATE_OFFER` | 이미 해당 요청에 지원했습니다. | |
| 409 | `DUPLICATE_PROPOSAL_REPORT` | 이미 해당 요청을 신고했습니다. | |
| 409 | `OFFER_NOT_ACCEPTABLE` | 수락할 수 없는 지원 상태입니다. | |
| 409 | `OFFER_NOT_CANCELLABLE` | 취소할 수 없는 지원 상태입니다. | |
| 409 | `OUTBOX_DELIVERY_NOT_RETRYABLE` | DEAD 상태인 전달만 다시 처리할 수 있습니다. | 관리자 웹 전용 |
| 409 | `MISSION_NOT_RESOLVABLE` | 분쟁 중인 임무만 판정할 수 있습니다. | 관리자 웹 전용 |
| 409 | `MISSION_NOT_SETTLEABLE` | 수행비를 지급할 수 없는 임무 상태입니다. | 관리자 웹 전용 |
| 409 | `OFFER_NOT_UPDATABLE` | 변경할 수 없는 지원 상태입니다. | |
| 409 | `PHONE_ALREADY_EXISTS` | 이미 가입된 휴대폰 번호입니다. | |
| 409 | `PROPOSAL_NOT_CANCELLABLE` | 취소할 수 없는 요청 상태입니다. | |
| 409 | `PROPOSAL_NOT_EDITABLE` | 수정할 수 없는 요청 상태입니다. | |
| 409 | `PROPOSAL_NOT_MATCHABLE` | 매칭할 수 없는 요청 상태입니다. | |
| 409 | `PROPOSAL_NOT_OPEN` | 지원을 받을 수 없는 요청 상태입니다. | |
| 409 | `PROPOSAL_NOT_REPORTABLE` | 신고할 수 없는 요청 상태입니다. | |
| 409 | `PROPOSAL_NOT_UPDATABLE` | 업데이트할 수 없는 요청 상태입니다. | |
| 409 | `PROPOSAL_REPORT_NOT_REVIEWABLE` | 이미 처리된 신고입니다. | |
| 409 | `SETTLEMENT_ACCOUNT_REQUIRED` | 요청 또는 지원을 등록하려면 정산 계좌를 먼저 등록해야 합니다. | 요청·지원 등록 전 계좌 필요 |
| 409 | `USER_WITHDRAWAL_BLOCKED` | 진행 중인 요청이나 지원, 완료되지 않은 환불 또는 정산이 있어 탈퇴할 수 없습니다. 모든 절차가 완료된 후 다시 이용해주세요. | 사유를 특정하지 못했을 때의 기본값 |
| 409 | `USER_WITHDRAWAL_BLOCKED_PROPOSAL_DEPOSIT` | 입금 확인 중인 요청이 있어 탈퇴할 수 없습니다. 확인이 끝난 후 다시 이용해주세요. | |
| 409 | `USER_WITHDRAWAL_BLOCKED_PROPOSAL` | 진행 중인 요청이 있어 탈퇴할 수 없습니다. 요청이 모두 종료된 후 다시 이용해주세요. | |
| 409 | `USER_WITHDRAWAL_BLOCKED_OFFER` | 진행 중인 지원이 있어 탈퇴할 수 없습니다. 지원이 모두 종료된 후 다시 이용해주세요. | |
| 409 | `USER_WITHDRAWAL_BLOCKED_REFUND` | 환불 처리가 끝나지 않아 탈퇴할 수 없습니다. 환불이 완료된 후 다시 이용해주세요. | |
| 409 | `USER_WITHDRAWAL_BLOCKED_PAYOUT` | 수행비 지급이 끝나지 않아 탈퇴할 수 없습니다. 지급이 완료된 후 다시 이용해주세요. | |
| 429 | `PHONE_VERIFICATION_SEND_RATE_LIMITED` | 인증번호 요청이 너무 많습니다. 잠시 후 다시 시도해주세요. | |
| 429 | `ADMIN_LOGIN_LOCKED` | 로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요. | 관리자 웹 전용. 연속 실패 5회에서 10분 잠금 |
| 500 | `INTERNAL_SERVER_ERROR` | 서버 내부 오류가 발생했습니다. | |
| 500 | `SMS_SENDER_NOT_CONFIGURED` | SMS 발신 설정이 완료되지 않았습니다. | |

내부 enum은 57개지만 실제로 나가는 wire code는 **51개**다. 인증 실패 5종, 사용자 부재 2종,
검증 실패 2종이 각각 하나의 코드로 합쳐지기 때문이며, 클라이언트는 enum 이름이 아니라 위 표의 code 기준으로 매핑한다.

## 탈퇴 차단 사유

`DELETE /v1/user`는 탈퇴가 막힌 이유마다 다른 코드를 낸다. 전부 409이고 `message`는 그대로
토스트에 쓸 수 있다. 안내 화면이나 이동 경로를 사유별로 다르게 하려면 `code`로 분기한다.

| code | 언제 |
|---|---|
| `USER_WITHDRAWAL_BLOCKED_PROPOSAL_DEPOSIT` | 입금 확인 대기(`HOLDING`) 요청이 있을 때 |
| `USER_WITHDRAWAL_BLOCKED_PROPOSAL` | 그 밖의 종결되지 않은 요청이 있을 때 |
| `USER_WITHDRAWAL_BLOCKED_OFFER` | 종결되지 않은 지원이 있을 때 |
| `USER_WITHDRAWAL_BLOCKED_REFUND` | 환불이 대조 대기 또는 이체 대기일 때(`REFUND_PENDING` 요청 포함) |
| `USER_WITHDRAWAL_BLOCKED_PAYOUT` | 수행비 지급이 남아 있을 때 |
| `USER_WITHDRAWAL_BLOCKED` | 사유를 특정하지 못했을 때의 기본값 |

차단 조건이 여러 개면 요청 → 지원 → 환불 → 수행비 순으로 먼저 걸린 하나만 나간다.

사유 없는 `USER_WITHDRAWAL_BLOCKED`는 안전망이다. 탈퇴 차단은 종결 상태 화이트리스트로
판정하므로 새 상태는 전용 코드가 붙기 전에도 차단되며, 그 구간을 이 코드가 메운다.
그래서 **클라이언트는 모르는 `USER_WITHDRAWAL_BLOCKED*` 코드를 만나면 `message`를 그대로
보여주는 기본 처리로 떨어져야 한다.** 판정 규칙은
[`../domains/user-auth/withdrawal-policy.md`](../domains/user-auth/withdrawal-policy.md)에 있다.


## Swagger(`/docs`)와의 관계

50개 코드 중 48개는 각 엔드포인트의 실패 응답 예시로 `openapi.json`에 들어 있다.
`NOT_FOUND`·`METHOD_NOT_ALLOWED`는 매칭되는 엔드포인트가 없을 때만 발생해 특정 오퍼레이션에 속할 수 없으므로,
개별 API 문서 대신 API 설명(`info.description`) 상단에 문서화한다.

`INTERNAL_SERVER_ERROR`는 모든 오퍼레이션의 500 응답에 자동으로 주입된다
(`app/core/openapi.py`의 `apply_global_error_responses()`).

이 대응은 `tests/test_openapi.py`가 검증한다. 카탈로그에 코드를 추가하면 어딘가에 문서화하기 전까지 테스트가 실패한다.

## 봉투를 타는 특수 상황

| 상황 | HTTP | code |
|---|---|---|
| 존재하지 않는 경로 | 404 | `NOT_FOUND` |
| 허용되지 않은 HTTP 메서드 | 405 | `METHOD_NOT_ALLOWED` |
| 서버 내부 미처리 예외 | 500 | `INTERNAL_SERVER_ERROR` |

`INTERNAL_SERVER_ERROR`의 `details`는 `APP_DEBUG=true`인 환경에서만 예외 문자열을 담고,
운영 환경에서는 항상 `null`이다.


## `HTTP_ERROR` — 42번째 값

`error.code`의 스키마 열거형(`ErrorCode`)은 위 표의 50개에 `HTTP_ERROR` 하나를 더해 51개다.

`HTTP_ERROR`는 카탈로그를 거치지 않은 `HTTPException`이 봉투를 탈 때만 나가는 방어용 값이다.
HTTP 상태는 원래 예외의 것을 그대로 유지하고, 메시지는 `요청을 처리할 수 없습니다.`로 고정된다.

**현재 서버 코드에는 이 값을 발생시키는 경로가 없다.** 모든 에러는 `api_error()`를 거치며,
`tests/test_errors.py`가 raw `HTTPException` 사용을 금지해 이를 강제한다.
그래도 열거형에 두는 이유는, 향후 누군가 카탈로그를 우회했을 때 스키마가 약속한 값 집합을
응답이 어기지 않게 하기 위해서다.

클라이언트는 이 코드를 일반 오류 안내로 처리하면 된다. 관측되면 서버 버그이므로 백엔드에 알린다.

## SMS 발송 실패에 대한 코드가 없는 이유

인증번호 발송은 응답이 나간 뒤 background task로 실행된다. 응답 시점에는 발송을 시도하기도
전이라 실패를 HTTP 응답으로 돌려줄 방법이 없다. 발송 실패는 서버 로그로만 남고 클라이언트는
정상 응답을 받는다.

과거 스펙에 있던 502 `SMS_SEND_FAILED`는 비동기 발송 전환(커밋 `284fd4a`) 시점에
`SMS provider 실패는 요청 응답을 실패시키지 않고 verification 을 유지한다`로 대체되면서
폐기됐다. 카탈로그에 남아 있던 정의는 2026-08-20에 제거했다. **누락이 아니라 폐기다.**
