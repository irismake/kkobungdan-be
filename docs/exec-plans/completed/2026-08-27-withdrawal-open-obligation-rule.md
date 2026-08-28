# 탈퇴 차단 조건을 미결(open) 판정 하나로 통일

작성일: 2026-08-27 · 상태: 구현·MySQL 통합 검증·문서 갱신 완료

## 배경

탈퇴 차단 조건이 상태 열거 방식으로 흩어져 있어 경우의 수를 셀 때마다 목록이 달라졌다.
"완료되지 않은 요청", "분쟁 중", "수행비 미지급", "지원한 offer"가 각각 별도 규칙처럼 보였지만,
실제로는 하나의 술어로 접힌다.

탈퇴는 `settlement_accounts`(환불·지급 계좌)와 `phone`을 하드 삭제한다. 따라서 차단의 본질은
"거래가 진행 중이냐"가 아니라 **"그 개인정보가 아직 필요한 상태냐"** 이고, 그것은 곧 사용자에게
걸린 애그리거트가 종결되지 않았다는 뜻이다.

### 기존 구현의 구멍 두 가지

1. `REFUND_PENDING` Proposal이 차단 목록에 없다. 지금은 `PENDING` Refund 조회가 우연히
   덮고 있을 뿐이라, Refund row 없이 `REFUND_PENDING`이 되는 경로가 생기면 뚫린다.

2. `HOLDING` 자동취소가 자기모순이다. 자동취소는 `REVIEW` Refund를 남기는데
   (`user_withdrawal_service.py`), 그 자리에서 계좌와 전화번호를 지운다. 나중에 관리자가
   대조해 입금이 확인되면 `REVIEW → PENDING`으로 환불 의무가 확정되지만 보낼 계좌도
   연락할 번호도 없다. `PENDING` Refund를 차단하는 이유와 같은 사고가 시점만 탈퇴 이후로
   밀린 것이다.

   더구나 사용자가 `HOLDING`을 직접 취소해도 `CANCELLED` + `REVIEW`가 되어 `REVIEW`를 차단
   조건에 넣는 순간 똑같이 막힌다. 즉 자동취소를 하든 안 하든 탈퇴 가능 여부는 같고,
   차이는 사용자가 요청을 잃는다는 것뿐이다. 이득 없는 파괴적 부수효과다.

## 결정 내용

### 1. 차단 판정을 종결 상태 화이트리스트로 뒤집는다

차단 상태를 열거하지 않고 **종결 상태를 열거하고 나머지를 전부 미결로 본다.** 상태가 추가될 때
기본값이 안전한 쪽(차단)으로 잡히게 하기 위해서다.

```
탈퇴 차단 = ∃ A ∈ {Proposal, Offer, Mission, Refund} where A.is_open
A.is_open ≡ A.status ∉ TERMINAL(A)
```

| 애그리거트 | 기준 사용자 | 종결(TERMINAL) |
|---|---|---|
| Proposal | `orderer_id` | `ALL_COMPLETED` `REFUNDED` `CANCELLED` `REPORTED` |
| Offer | `runner_id` | `ALL_COMPLETED` `REJECTED` `CANCELLED` |
| Mission | `runner_id` | `PAID` `FAILED`, 또는 `COMPLETED` + 지급 반려 |
| Refund | `orderer_id` | `COMPLETED` `VOIDED` |

Mission은 상태만으로 부족하다. `COMPLETED`는 수행비 지급 대기 상태로 남아 있을 수 있어
`settlement_status`(`PayoutStatus`)까지 봐야 한다. 지급 완료는 `PAID`로 전이하므로
`COMPLETED`로 남아 종결인 경우는 반려(`settlement_rejected_at`)뿐이다.

행님 쪽 Mission은 따로 보지 않는다. Mission `STARTED`/`DISPUTED`는 Proposal
`MATCHED`/`ORDER_COMPLETED`/`DISPUTED`와 1:1이고, `FAILED` Mission의 행님 환불 의무는
Refund가 들고 있다. 두 축 모두 위 표에서 이미 차단된다.

### 2. `HOLDING`을 자동취소에서 차단으로 옮긴다

`HOLDING`은 "입금 여부를 아직 모른다"는 뜻이다. `REVIEW`와 같은 불확실성이고, 확정된
`PENDING`/`REFUND_PENDING`과 대우를 달리할 근거가 없다. 넷 다 "우리 쪽에 돈이 있거나, 있는지
모른다"는 한 가지 이유로 묶인다.

자동취소 집합에는 Offer `WAITING`만 남는다. 러너의 지원은 돈이 오간 적이 없어 탈퇴 트랜잭션
안에서 종결시킬 수 있다.

| 분류 | 판단 기준 | 해당 |
|---|---|---|
| 자동취소 | 돈이 개입된 적 없음 | Offer `WAITING` |
| 차단 | 그 외 모든 미결 | 나머지 전부 |

`HOLDING` Proposal에 달린 대기 Offer를 함께 취소하던 경로는 사라진다. `HOLDING`이 차단이라
그 지점에 도달하지 않는다.

### 3. 대기 구간은 감수한다

`HOLDING` 사용자는 즉시 탈퇴할 수 없다. `created_at` 기준 24시간이 지나면
`payment_checker.py`가 자동 만료시키고(`CANCELLED` + `REVIEW`), 그 뒤 관리자 대조까지가 대기
구간이다. 입금하지 않은 사용자에게는 불필요한 대기지만, **입금 여부를 알 수 없다는 것이
`HOLDING`의 정의**라 코드로 구분할 방법이 없다. 운영자가 수동으로 대조를 앞당겨 완화한다.

### 4. 에러 문구를 갱신한다

기존 문구는 "진행 중인 임무, 분쟁 또는 정산이 있어"인데, 입금 확인 대기는 진행 중인 임무가
아니라 문구가 사실과 어긋난다. 환불·입금 확인을 포함하도록 고친다.

## 작업 범위

- [x] `app/services/user_auth/user_withdrawal_service.py` — 화이트리스트 판정, `HOLDING` 차단, `REVIEW` 차단, Mission 지급 축 반영
- [x] `app/core/errors.py` — `USER_WITHDRAWAL_BLOCKED` 문구
- [x] `docs/domains/user-auth/withdrawal-policy.md` — 정책 정본 갱신
- [x] `docs/product-specs/error-copy-policy.md`, `docs/api-spec/error-codes.md` — 문구 동기화
- [x] `tests/test_user_auth_integration.py` — `HOLDING` 차단, `REVIEW` 차단, 지급 반려 허용 케이스

## 검증 결과

MySQL 통합 테스트로 확인했다. `pytest tests/test_user_auth_integration.py -k withdraw` 27건 통과.
전체 스위트는 322 passed / 1 failed이며, 실패한 `test_create_proposal_validation_errors`는 이
작업 이전부터 깨져 있던 건으로 범위 밖이다.

| 상황 | 기대 |
|---|---|
| `HOLDING` Proposal 보유 | 409 `USER_WITHDRAWAL_BLOCKED`, Proposal 상태 불변 |
| `CANCELLED` Proposal + `REVIEW` Refund | 409 차단 |
| `CANCELLED` Proposal + `VOIDED` Refund | 탈퇴 허용 |
| `REFUND_PENDING` Proposal (Refund row 없음) | 409 차단 |
| `WAITING` Offer만 보유 | 탈퇴 허용, Offer `CANCELLED` |
| `COMPLETED` Mission + 지급 반려 | 탈퇴 허용 |
| `COMPLETED` Mission + 지급 대기 | 409 차단 |
| `FAILED` Mission 보유 꼬붕 | 탈퇴 허용 |

## 후속

- ~~차단 사유별 문구 분기~~ → 같은 브랜치에서 이어서 처리했다. 차단 사유마다 wire code를 나누고
  (`USER_WITHDRAWAL_BLOCKED_PROPOSAL_DEPOSIT` 등 5종 + 기본값 1종) `message`를 사유에 맞게 낸다.
  `details`는 쓰지 않는다. 앱이 읽지 않는 필드이고, `error-codes.md`가 `code`를 분기의 유일한
  기준으로 못박고 있기 때문이다. `INVALID_TOKEN`처럼 한 코드에 문구를 몰아넣는 방식은 같은
  문서가 이미 "코드만 보고 강제 로그아웃하면 안 된다"는 주의사항으로 다루고 있어 따르지 않았다.

  `REFUND_PENDING` Proposal은 Proposal 검사에 먼저 걸리지만 사용자가 기다리는 것은 환불이므로
  환불 코드로 보낸다.

  판정이 `bool`에서 사유로 바뀌면서 `_has_blocking_activity`는 `_find_blocking_error`가 됐다.
  OpenAPI는 대표 코드 하나만 라우터에 적고 변형을 펼치도록 `error_responses`에 `_ERROR_VARIANTS`
  확장을 두어 `INVALID_TOKEN`의 하드코딩도 같은 자리로 합쳤다.

  클라이언트는 모르는 `USER_WITHDRAWAL_BLOCKED*` 코드를 만나면 `message`를 그대로 보여주는 기본
  처리로 떨어져야 한다. 화이트리스트 판정이라 새 상태는 전용 코드가 붙기 전에도 차단된다.

- 문구가 모두 두 문장이라 토스트에 길다는 문제는 그대로 남는다.
  `error-copy-policy.md`의 "문구 검토 필요"에 둔다.
