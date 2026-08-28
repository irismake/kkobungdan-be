# 회원 탈퇴 정책

회원 탈퇴 시 개인정보와 인증·연락 수단은 즉시 hard delete한다. 거래 이력의 참조 무결성을 위해 `users` row와 비식별 활동 기록만 유지하며, 로그인과 일반 API 접근은 즉시 차단한다.

## 기본 원칙

- `users` row는 삭제하지 않고 `deleted = true`, `deleted_at = now`로 표시한다.
- 사용자 이름, 전화번호, 전화번호 인증 시각, 마지막 로그인 시각, 비밀번호 해시, 알림 설정은 `null`로 영구 삭제한다.
- 탈퇴 사용자의 이름은 저장하지 않고, 활동 조회 응답에서만 `탈퇴한 사용자`로 표시한다.
- 탈퇴 후 같은 전화번호 재가입은 허용한다.
- Proposal, Offer, DisputeEvidence 같은 거래 활동 기록은 삭제하지 않는다.
- 탈퇴 사유 선택 이력은 개인정보 삭제와 별도로 `user_withdrawals`에 보존한다.

## 탈퇴 차단 판정

탈퇴는 환불·지급 계좌(`settlement_accounts`)와 전화번호를 하드 삭제한다. 따라서 차단 기준은
"거래가 진행 중이냐"가 아니라 **"그 개인정보가 아직 필요하냐"** 이고, 그건 곧 사용자에게 걸린
애그리거트가 종결되지 않았다는 뜻이다. 판정은 하나의 술어로 정의한다.

```
탈퇴 차단 = ∃ A ∈ {Proposal, Offer, Mission, Refund} where A가 미결
A가 미결 ≡ A의 상태가 종결 집합에 없음
```

차단 상태를 열거하지 않고 **종결 상태를 열거하고 나머지를 전부 미결로 본다.** 상태가 새로
추가될 때 기본값이 안전한 쪽(차단)으로 잡히게 하기 위해서다. 상태를 추가·변경하면 아래 종결
집합을 함께 갱신한다.

| 애그리거트 | 기준 사용자 | 종결(탈퇴 허용) |
|---|---|---|
| Proposal | `orderer_id` | `ALL_COMPLETED` `REFUNDED` `CANCELLED` `REPORTED` |
| Offer | `runner_id` | `ALL_COMPLETED` `REJECTED` `CANCELLED` (`WAITING`은 자동 취소) |
| Mission | `runner_id` | `PAID` `FAILED`, 또는 `COMPLETED` + 수행비 지급 반려 |
| Refund | `orderer_id` | `COMPLETED` `VOIDED` |

미결이면 탈퇴 요청을 `USER_WITHDRAWAL_BLOCKED`로 차단한다. 상대방 거래 경험, 고객센터 대응,
분쟁 처리, 정산 확인이 남을 수 있고, 무엇보다 환불·지급 계좌가 아직 필요하기 때문이다.

### 애그리거트별 근거

**Proposal**: `HOLDING` `POSTED` `OFFERED` `MATCHED` `ORDER_COMPLETED` `DISPUTED`
`REFUND_PENDING`이 미결이다. `HOLDING`은 입금 여부를 아직 모르는 상태이므로 차단한다
(아래 참고).

**Offer**: `ACCEPTED` `RUNNER_COMPLETED` `DISPUTED`가 미결이다. `WAITING`은 돈이 오간 적이
없어 탈퇴와 함께 자동 취소한다.

**Mission**: 상태만으로 부족하다. `COMPLETED`는 수행비 지급 대기로 남아 있을 수 있어
지급 시각·반려 시각까지 본다. 지급 완료는 `PAID`로 전이하므로 `COMPLETED`로 남아 종결인
경우는 반려뿐이다. 행님 쪽 Mission은 따로 보지 않는다. `STARTED`/`DISPUTED`는 Proposal
`MATCHED`/`ORDER_COMPLETED`/`DISPUTED`와 1:1이고, `FAILED` Mission의 행님 환불 의무는
Refund가 들고 있어 두 축 모두 이미 차단된다.

**Refund**: `REVIEW`와 `PENDING`이 미결이다. `PENDING`은 환불 의무가 확정됐는데 이체가 안
끝난 상태고, `REVIEW`는 입금 여부를 모르는 상태다. 둘 다 계좌가 필요하므로 대우를 달리하지
않는다. 대조 결과 입금이 없으면 `VOIDED`로 종결되어 차단이 풀린다.

### 차단 사유별 코드

차단 응답은 사유마다 코드를 나눈다. 사용자가 겪는 상황이 "입금 확인을 기다리는 중"과 "거래가
진행 중"과 "돈을 받을 차례"로 갈리는데, 한 문구로는 무엇을 기다려야 하는지 알 수 없기 때문이다.
앱은 `code`로 분기하고 `message`를 토스트로 그대로 쓴다.

| 판정 | code |
|---|---|
| `HOLDING` Proposal | `USER_WITHDRAWAL_BLOCKED_PROPOSAL_DEPOSIT` |
| `REFUND_PENDING` Proposal | `USER_WITHDRAWAL_BLOCKED_REFUND` |
| 그 밖의 미결 Proposal | `USER_WITHDRAWAL_BLOCKED_PROPOSAL` |
| 미결 Offer | `USER_WITHDRAWAL_BLOCKED_OFFER` |
| 미결 Refund | `USER_WITHDRAWAL_BLOCKED_REFUND` |
| 지급 대기 Mission | `USER_WITHDRAWAL_BLOCKED_PAYOUT` |

`REFUND_PENDING`은 Proposal 검사에 먼저 걸리지만 사용자가 기다리는 것은 환불이므로 환불 코드로
보낸다. 그 밖의 판정 순서는 Proposal → Offer → Refund → Mission이고, 먼저 걸린 사유 하나만
나간다. 문구 정본은 `app/core/errors.py`이며 목록은
[`error-codes.md`](../../api-spec/error-codes.md#탈퇴-차단-사유)에 있다.

## `HOLDING`을 자동 취소하지 않는 이유

`HOLDING` Proposal을 탈퇴와 함께 자동 취소하면 `REVIEW` Refund를 남긴 채 계좌와 전화번호를
지우게 된다. 나중에 관리자가 대조해 입금이 확인되면 `REVIEW → PENDING`으로 환불 의무가
확정되지만, 보낼 계좌도 연락할 번호도 없다. `PENDING` Refund를 차단하는 이유와 같은 사고가
시점만 탈퇴 이후로 밀린 것이다.

더구나 사용자가 `HOLDING`을 직접 취소해도 `CANCELLED` + `REVIEW`가 되어 똑같이 차단된다.
자동 취소를 하든 안 하든 탈퇴 가능 여부는 같고, 차이는 사용자가 요청을 잃는다는 것뿐이다.
이득 없는 파괴적 부수효과라 자동 취소 대상에서 제외한다.

대신 `HOLDING` 사용자는 즉시 탈퇴할 수 없다. `created_at` 기준 24시간이 지나면 입금 마감
자동 취소로 `CANCELLED` + `REVIEW`가 되고, 그 뒤 관리자 대조까지가 대기 구간이다. 입금하지
않은 사용자에게는 불필요한 대기지만, **입금 여부를 알 수 없다는 것이 `HOLDING`의 정의**라
코드로 구분할 방법이 없다. 운영자가 대조를 앞당겨 완화한다.

## 탈퇴 시 자동 취소 상태

돈이 개입된 적 없는 활동만 탈퇴 트랜잭션 안에서 종결시킨다. 현재 대상은 하나다.

- Offer `WAITING` — 러너의 대기 중인 지원. 입금과 무관하다.

## 즉시 정리 데이터

탈퇴 직후 즉시 삭제한다.

- `user_fcm_tokens`
- 탈퇴 사용자 전화번호 기준 `auth_phone_verifications`
- `settlement_accounts`
- `notifications`

`settlement_accounts`는 계좌 개인정보이므로 탈퇴 완료 시 삭제한다. 단, 미결 환불·수행비 지급이
있으면 위 차단 조건에 따라 탈퇴 자체를 허용하지 않아 처리 전에 계좌가 사라지지 않게 한다.

## 보존 데이터

즉시 삭제하지 않는다.

- `users` soft-deleted row
- `user_withdrawals`
- `proposals`
- `offers`
- `dispute_evidences`
- `terms_agreements`

## 탈퇴 사유

`GET /v1/user/withdrawal-reasons`는 활성 탈퇴 사유를 표시 순서대로 반환한다.

기본 탈퇴 사유:

- 원하는 임무가 많지 않았어요.
- 원하는 꼬붕(또는 행님)을 만나기 어려웠어요.
- 이용 방법이 어려웠어요.
- 앱이 자주 오류가 났어요.
- 다른 회원과 문제가 있었어요.
- 다른 서비스를 이용하려고 해요.
- 기타

`DELETE /v1/user`는 `reasonQuestionId`를 필수로 받고 `detailReason`은 선택으로 받는다. body 없이
호출하거나 `reasonQuestionId`가 없으면 `VALIDATION_ERROR`다. `reasonQuestionId`가 활성 사유가 아니어도
`VALIDATION_ERROR`를 반환한다. 사유의 `requires_detail`이 `true`(=`기타`)이면 `detailReason`을 필수로 요구한다.

이 정책은 탈퇴 전용이 아니다. 게시글 신고(`POST /v1/proposal/{id}/reports`)와 분쟁 접수
(`POST /v1/proposal/{id}/dispute`, `POST /v1/offer/{offerId}/dispute`)도 같은 규칙을 쓴다.

## API 공개 상태

`GET /v1/user/withdrawal-reasons`는 인증된 사용자에게 탈퇴 사유 목록을 제공한다.

`DELETE /v1/user`는 인증된 사용자의 탈퇴 요청을 처리한다.
