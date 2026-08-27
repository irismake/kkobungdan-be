# 미확인 입금 취소 건 환불 누락 해결

작성일: 2026-08-26 · 상태: 구현·MySQL 통합 검증·문서 갱신 완료

## 배경

`HOLDING`은 관리자가 입금을 수동으로 확인하기 전 상태다. 실제 입금 시각과 관리자 확인
시각 사이에는 시차가 있는데, 기존 정책은 "관리자 확인 = 실제 입금 여부"로 가정하고
`HOLDING` 취소를 환불 없이 `CANCELLED`로 종결했다.

그래서 행님이 입금한 뒤 관리자가 확인하기 전에 요청을 취소하면 돈은 계좌에 들어와 있는데
시스템에는 환불 대상이 남지 않는다. 24시간 입금 마감 자동취소도 같은 구멍을 가진다.

사용자에게 입금 여부를 묻는 방식은 검증할 수 없는 입력이라 채택하지 않는다. 관리자가
계좌 내역으로 판단한다.

## 결정 내용

`RefundStatus`에 환불 확정 이전 단계인 `REVIEW`를 추가하고, 입금이 없었음을 확인한 종결
상태로 `VOIDED`를 추가한다.

```
REVIEW → PENDING → COMPLETED
   └───→ VOIDED
```

- `REVIEW`: 입금 대조 대기. 환불 대상인지 아직 모른다.
- `PENDING`: 환불 의무 확정. 이체만 남았다.
- `VOIDED`: 대조 결과 입금이 없어 종결. 반려가 아니라 애초에 받은 돈이 없다는 뜻이다.

`refund-lifecycle.md`의 "환불은 확정된 의무이므로 반려하지 않는다"는 `PENDING` 이후에
적용된다. `REVIEW`는 그 앞단이다.

### 상태 전이

| 취소 경로 | Proposal | Refund |
|---|---|---|
| `HOLDING` 사용자 취소 | `CANCELLED` | `REVIEW` / `USER_CANCELLED` |
| `HOLDING` 입금 마감 자동취소 | `CANCELLED` | `REVIEW` / `PAYMENT_EXPIRED` |
| `HOLDING` 관리자 취소 | `CANCELLED` | `REVIEW` / `ADMIN_CANCELLED` |
| `HOLDING` 탈퇴 자동취소 | `CANCELLED` | `REVIEW` / `USER_CANCELLED` |
| `POSTED`/`OFFERED` 취소 | `REFUND_PENDING` | `PENDING` (기존과 동일) |

`RefundReason.PAYMENT_EXPIRED`를 추가한다. 자동취소는 행님이 취소를 누른 것도 관리자가
취소한 것도 아니라 기존 사유로 표현하면 사실과 다르다.

### 관리자 대조

| 판정 | Refund | Proposal |
|---|---|---|
| 입금 있음 | `REVIEW` → `PENDING` | `CANCELLED` → `REFUND_PENDING` |
| 입금 없음 | `REVIEW` → `VOIDED` | `CANCELLED` 유지 |

입금이 확인되면 Proposal을 `REFUND_PENDING`으로 올려 기존 환불 완료 흐름
(`complete_refund` → `REFUNDED`)을 그대로 태운다. 완료 처리 경로를 두 벌 만들지 않기
위해서다.

`void`는 돈을 지급하지 않고 종결하는 유일한 경로이므로 `adminNote`를 필수로 받는다.

## 작업 항목

1. `RefundStatus`에 `REVIEW`, `VOIDED` / `RefundReason`에 `PAYMENT_EXPIRED` 추가
2. `Refund.confirm_deposit()`, `Refund.void()` 추가
3. `Proposal.confirm_late_deposit()` 추가 (`CANCELLED` → `REFUND_PENDING`)
4. `RefundService.create_review()` 추가
5. `ProposalService.cancel` / `cancel_expired_payment_proposals` / `AdminCommandService.cancel_proposal`의 `HOLDING` 분기에서 `REVIEW` 생성
6. 관리자 API 2개 추가
   - `POST /v1/admin/refund/{refundId}/confirm-deposit`
   - `POST /v1/admin/refund/{refundId}/void`
7. Alembic 마이그레이션: `refunds.status`, `refunds.reason` CHECK 제약 갱신
8. 문서 갱신: `refund-lifecycle.md`, `domain.md`, `docs/api-spec/README.md`
9. 테스트

## 검증 기준

- `HOLDING` 취소 시 Proposal은 `CANCELLED`이고 `REVIEW` 환불이 생긴다
- 입금 마감 자동취소도 `REVIEW` 환불을 만든다
- `confirm-deposit` 후 Proposal이 `REFUND_PENDING`이고 기존 `complete`로 `REFUNDED`까지 간다
- `void`는 `adminNote` 없이는 400, 처리 후 Proposal은 `CANCELLED`로 남는다
- `REVIEW` 환불에 `complete`를 호출하면 `REFUND_NOT_PROCESSABLE`
- 대시보드 미처리 환불 수는 `PENDING`만 센다
- `POSTED`/`OFFERED` 취소와 분쟁 환불 흐름은 회귀 없이 동작한다

## 추가: 대시보드 집계

`AdminSummaryResponse.refundCount`는 `PENDING`만 센다(대시보드 카운트는 `PENDING`만 센다는
결정 유지). 대신 `depositReviewCount`를 새로 추가해 `REVIEW` 건수를 별도로 노출한다.
`refundCount`에 합치면 "환불 밀림" 지표가 실제보다 부풀어 보이기 때문이다.

## 검증 결과

- `pytest` 전체: 313 passed, 2 failed
- 실패 2건(`test_create_proposal_validation_errors`,
  `test_withdraw_user_rolls_back_all_changes_when_anonymization_fails`)은 이 작업 이전부터
  실패하던 건이다. 변경 전 커밋에서도 동일하게 실패하는 것을 확인했다.
- Alembic `0031`을 빈 MySQL 8 스키마에 upgrade/downgrade 양방향으로 적용해 `refunds`의
  두 CHECK 제약이 의도한 값 목록으로 바뀌는 것을 확인했다.

## 남는 문제

관리자 대조는 여전히 수동이다. `REVIEW` 대부분은 실제 미입금이라 `VOIDED`로 끝난다.
물량이 커지면 관리자 웹에 일괄 `void` 처리가 필요하다. 근본 해결은 PG 결제 도입이다.

탈퇴 자동취소도 `REVIEW`를 남기지만, 탈퇴는 PII를 하드 삭제하므로 이후 입금이 확인되어도
이체할 계좌가 남지 않는다. 기록은 남겨 추적은 가능하게 했으나 지급 경로는 없다. `REVIEW`를
탈퇴 차단 조건에 넣는 방안은, 대부분이 실제 미입금이라 정상 사용자의 탈퇴를 대조가 끝날
때까지 막게 되므로 채택하지 않았다. 정책 판단이 필요하면 다시 다룬다.
