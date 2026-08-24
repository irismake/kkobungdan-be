# 환불 수명주기와 분쟁 종결 상태

## 문제 정의

기존 환불 API는 `FAILED` 미션을 환불로 투영한다. 이 구조는 수락된 지원이 있는 분쟁 환불은
표현할 수 있지만, 입금 확인 후 아직 지원이 수락되지 않은 `POSTED`/`OFFERED` 요청의 취소는
미션이 없어서 환불 목록에 넣을 수 없다. 또한 분쟁 해결 뒤 Proposal과 Offer를 모두
`RESOLVED`로 두면 앱이 표시해야 하는 실제 결과인 완료 또는 취소를 알기 어렵다.

## 배경과 제약

- 미션은 Offer 수락 시점에만 생성한다.
- 입금 확인된 요청의 수행비는 매칭 전 취소라도 행님에게 환불해야 한다.
- 분쟁 처리 기록의 상태와 앱에서 표시할 요청·지원의 최종 상태는 서로 다른 관심사다.
- 실제 이체는 관리자가 수행하며 환불 대상 확정과 환불 완료는 별도 시점이다.

## 결정 내용

### 분쟁 종결

`RESOLVED`는 `DisputeEvidence.status`에서 분쟁 검토가 끝났다는 뜻으로만 사용한다. 새 분쟁
처리는 Proposal/Offer를 `RESOLVED`로 전이하지 않는다.

| 관리자 판정 | Proposal | Offer | Mission | 후속 처리 |
|---|---|---|---|---|
| 행님 책임 (`COMPLETED`) | `ALL_COMPLETED` | `ALL_COMPLETED` | `COMPLETED` | 꼬붕 수행비 지급 |
| 꼬붕 책임 (`FAILED`) | `REFUND_PENDING` | `CANCELLED` | `FAILED` | 행님 환불 |

환불 이체가 끝나면 Proposal은 `REFUNDED`가 된다. 앱은 `REFUND_PENDING`과 `REFUNDED`를
모두 취소 영역에 표시하되, 필요한 경우 환불 진행 여부를 구분할 수 있다.
`ProposalStatus.RESOLVED`와 `OfferStatus.RESOLVED`는 제거하고 기존 데이터도 실제 판정 결과로
마이그레이션한다.

### 매칭 전 취소

- `HOLDING`은 입금 확인 전이므로 바로 `CANCELLED`로 종결하고 환불을 만들지 않는다.
- `POSTED`/`OFFERED`는 입금 확인 후이므로 `REFUND_PENDING`으로 전이하고 환불을 만든다.
- 연결된 `WAITING` Offer는 기존 정책대로 `REJECTED`로 정리한다.
- 환불 완료 시 Proposal은 `REFUNDED`로 전이한다.

### 매칭 후 관리자 취소

관리자는 분쟁 없이도 요청을 취소할 수 있다. 미션에는 취소 상태가 없으므로 환불 대상인
`FAILED`로 종결한다.

| 취소 시점 | Proposal | Offer | Mission | Refund |
|---|---|---|---|---|
| `HOLDING` | `CANCELLED` | `WAITING` → `REJECTED` | 없음 | 만들지 않음 |
| `POSTED`/`OFFERED` | `REFUND_PENDING` | `WAITING` → `REJECTED` | 없음 | `ADMIN_CANCELLED` |
| `MATCHED`/`ORDER_COMPLETED` | `REFUND_PENDING` | 수행 중 Offer → `CANCELLED` | `FAILED` | `ADMIN_CANCELLED` |

미션이 이미 `COMPLETED`, `PAID`, `FAILED`인 요청은 취소를 거절한다. 지급이 끝났거나 이미
종결된 건을 되돌리지 않기 위해서다.

### Refund 정본

`refunds`를 환불 처리의 정본으로 둔다. 환불은 Proposal과 1:1이고, 수락 이후 환불이면
Mission을 선택적으로 참조한다. 관리자 환불 API의 `refundId`는 Refund ID다.

환불 원인은 다음 코드와 선택 상세로 분리한다.

| reason | 생성 경로 | reasonDetail |
|---|---|---|
| `USER_CANCELLED` | 행님이 입금 확인 후 매칭 전 취소 | 없음 |
| `ADMIN_CANCELLED` | 관리자가 요청 또는 미션 취소 | 관리자 취소 메모 |
| `DISPUTE_FAILED` | 분쟁을 꼬붕 책임으로 판정 | 사용자가 제출한 분쟁 사유 |

Refund는 `PENDING`, `COMPLETED` 처리 상태와 요청·처리 시각, 처리 관리자 및 메모를 기록한다.
환불은 확정된 의무이므로 반려하지 않는다. Mission은 실행 결과인 `FAILED`를 유지하며 환불 완료
여부나 환불 처리 필드를 소유하지 않는다.

## 고려한 대안

- Proposal에 환불 컬럼만 추가: 수락 이후 Mission 환불과 정본이 둘로 갈리고 관리자 API가
  두 테이블을 합쳐야 하므로 제외했다.
- 매칭 전에도 Mission 생성: Offer와 runner가 없는 수행 단위가 생겨 Mission 불변식을 깨므로
  제외했다.
- Proposal/Offer를 계속 `RESOLVED`로 유지: UI가 완료와 취소 결과를 추가 조합 없이 표현하지
  못하므로 제외했다.

## 롤아웃과 마이그레이션

- 기존 `FAILED`/`REFUNDED` Mission은 Refund로 백필하고 Mission 상태는 `FAILED`로 통일한다.
- 연결된 분쟁 증빙이 있으면 `DISPUTE_FAILED`, 없으면 `ADMIN_CANCELLED`로 분류한다.
- Mission 결과에 따라 기존 `RESOLVED` Proposal/Offer를 완료·환불·분쟁 상태로 변환한다. 기존
  미션에 판정 결과가 없어 `DISPUTED`인 건은 관리자 재판정 대상으로 남긴다.
- 기존 Mission 환불 API와 Mission 환불 컬럼은 제거한다.

## 리스크와 열린 질문

- 앱은 새 Proposal 상태 두 개를 취소 배지에 매핑해야 한다.
