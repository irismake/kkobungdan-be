# OrderRun 도메인 정책 정본

이 문서는 API 명세에서 참조하는 도메인 상태와 정책 해석의 기준이다.
외부 API 요청/응답 계약은 [`api-spec/README.md`](./api-spec/README.md)를 우선한다.

## ProposalStatus

Proposal은 행님 관점의 모집 및 수행 상태를 추적한다.

| 값 | 설명 |
|----|------|
| HOLDING | 입금 확인 대기 |
| POSTED | 모집 중 |
| OFFERED | 지원 도착 |
| MATCHED | Offer 수락으로 수행 건이 확정된 상태 |
| ORDER_COMPLETED | 행님이 완료 확인을 마친 상태 |
| ALL_COMPLETED | 꼬붕과 행님이 모두 완료 확인을 마친 상태 |
| DISPUTED | 분쟁 접수 |
| REFUND_PENDING | 취소가 확정되어 행님 환불을 기다리는 상태 |
| REFUNDED | 행님 환불이 완료된 상태 |
| REPORTED | 관리자 승인으로 신고 처리된 게시글 |
| CANCELLED | 입금 확인 전 취소되어 환불 없이 종결된 상태 |

### Proposal 상태 전이

| 전이 | 발생 시점 |
|------|-----------|
| `HOLDING -> POSTED` | 입금 또는 관리자 확인으로 모집이 공개될 때 |
| `POSTED -> OFFERED` | 첫 Offer가 생성될 때 |
| `OFFERED -> MATCHED` | 오더가 Offer 하나를 수락할 때 |
| `MATCHED -> ORDER_COMPLETED` | 행님이 Proposal에서 완료를 확인할 때 |
| `ORDER_COMPLETED + Offer RUNNER_COMPLETED -> ALL_COMPLETED` | 꼬붕과 행님 완료가 모두 접수될 때 |
| `MATCHED/ORDER_COMPLETED -> DISPUTED` | 행님 또는 꼬붕이 분쟁을 접수할 때 |
| `DISPUTED -> ALL_COMPLETED` | 행님 책임으로 분쟁이 종결되어 꼬붕 지급 대상이 될 때 |
| `DISPUTED -> REFUND_PENDING` | 꼬붕 책임으로 분쟁이 종결되어 행님 환불 대상이 될 때 |
| `POSTED/OFFERED -> REPORTED` | 관리자가 게시글 신고를 승인할 때 |
| `HOLDING -> CANCELLED` | 오더가 입금 확인 전 Proposal을 취소할 때 |
| `POSTED/OFFERED -> REFUND_PENDING` | 오더가 입금 확인 후 매칭 전 Proposal을 취소할 때 |
| `HOLDING -> CANCELLED` | 관리자가 입금 확인 전 Proposal을 취소할 때 |
| `POSTED/OFFERED/MATCHED/ORDER_COMPLETED -> REFUND_PENDING` | 관리자가 입금 확인된 Proposal을 취소할 때 |
| `REFUND_PENDING -> REFUNDED` | 관리자가 행님 환불 완료를 기록할 때 |
| `HOLDING -> CANCELLED` | 생성 후 24시간 안에 입금 확인이 되지 않아 스케줄러가 자동 취소할 때 |

관리자 취소는 미션이 `STARTED` 또는 `DISPUTED`일 때만 허용한다. 이미 `COMPLETED`, `PAID`,
`FAILED`인 미션이 붙어 있으면 취소를 거절한다.

## OfferStatus

Offer는 꼬붕 관점의 지원 및 수행 상태를 추적한다.

| 값 | 설명 |
|----|------|
| WAITING | 수락 대기 |
| ACCEPTED | 수락되어 수행 건 기준이 된 상태 |
| RUNNER_COMPLETED | 꼬붕이 완료와 증빙 업로드를 마친 상태 |
| ALL_COMPLETED | 꼬붕과 행님이 모두 완료 확인을 마친 상태 |
| DISPUTED | 분쟁 접수 |
| REJECTED | 거절됨 |
| CANCELLED | 꼬붕이 수락 전 취소했거나, 수행 중 분쟁·관리자 취소로 종결된 상태 |

### Offer 상태 전이

| 전이 | 발생 시점 |
|------|-----------|
| `WAITING -> ACCEPTED` | 오더가 해당 Offer를 수락할 때 |
| `ACCEPTED -> RUNNER_COMPLETED` | 꼬붕이 Offer에서 완료를 등록할 때 |
| `RUNNER_COMPLETED + Proposal ORDER_COMPLETED -> ALL_COMPLETED` | 꼬붕과 행님 완료가 모두 접수될 때 |
| `ACCEPTED/RUNNER_COMPLETED -> DISPUTED` | 행님 또는 꼬붕이 분쟁을 접수할 때 |
| `DISPUTED -> ALL_COMPLETED` | 행님 책임으로 분쟁이 종결될 때 |
| `DISPUTED -> CANCELLED` | 꼬붕 책임으로 분쟁이 종결될 때 |
| `WAITING -> REJECTED` | 같은 Proposal의 다른 Offer가 수락되거나 Proposal 취소로 대기 Offer가 정리될 때 |
| `WAITING -> CANCELLED` | 꼬붕이 수락 전 Offer를 취소할 때 |
| `ACCEPTED/RUNNER_COMPLETED/DISPUTED -> CANCELLED` | 관리자가 Proposal을 취소해 수행 중인 Offer가 함께 종결될 때 |

## DisputeEvidence

DisputeEvidence는 수행 중 분쟁이 접수될 때 남기는 분쟁 증빙 기록이다.
수행 상태의 정본은 Proposal/Offer이며, DisputeEvidence는 분쟁 사유와 선택한 설문 질문을 보관한다.

DisputeEvidence는 `proposalId`, `offerId`, `actorId`, `reason`, `surveyQuestionId`, `createdAt`을 가진다.
API 응답에서는 신고·탈퇴와 맞추어 `surveyQuestionId`를 `reasonQuestionId`로, `reason`을 `detailReason`으로 내보내고
설문 질문 문구를 `reasonQuestionText`로 함께 반환한다. 저장 컬럼명은 그대로 둔다.

분쟁 처리 상태는 `PENDING`, `RESOLVED`이며 요청·지원의 진행 상태와 다른 축이다.
`RESOLVED`는 관리자가 판정을 마쳤다는 뜻일 뿐이며, Proposal과 Offer는 `RESOLVED`로 전이하지
않는다. 최종 상태는 판정 결과에 따라 아래로 갈린다.

| 판정 | Proposal | Offer | Mission | 후속 |
|------|----------|-------|---------|------|
| `COMPLETED` (행님 책임) | `ALL_COMPLETED` | `ALL_COMPLETED` | `COMPLETED` | 꼬붕 수행비 지급 |
| `FAILED` (꼬붕 책임) | `REFUND_PENDING` | `CANCELLED` | `FAILED` | 행님 환불 |

분쟁 처리 상태는 `PENDING`, `RESOLVED` 둘뿐이다. 반려는 두지 않는다. 반려는 요청·지원·미션
상태를 바꾸지 않아 반려된 요청이 `DISPUTED`에 영구히 갇혔고, 관리자가 내릴 수 있는 결론은
위 두 판정뿐이기 때문이다. 판단을 보류할 때는 `PENDING`으로 둔다.

## MissionStatus

Mission은 수락된 Offer의 수행 단위이며 관리자 웹 전용이다. 상태는 Proposal/Offer 상태에서
파생하지만 상태별 조회를 위해 컬럼으로 실체화한다. 제품 정책은
[`product-specs/mission.md`](./product-specs/mission.md)가 정본이다.

| 값 | 설명 |
|----|------|
| STARTED | 지원 수락으로 수행이 시작된 상태 |
| DISPUTED | 요청 또는 지원이 분쟁으로 전환된 상태 |
| COMPLETED | 수행이 정상 종료되어 수행비 지급을 기다리는 상태 |
| PAID | 꼬붕 수행비 지급이 완료된 종료 상태 |
| FAILED | 수행이 실패로 확정된 종료 상태 |

### Mission 상태 전이

| 전이 | 발생 시점 |
|------|-----------|
| `STARTED -> COMPLETED` | Proposal과 Offer가 모두 `ALL_COMPLETED`가 될 때 |
| `STARTED -> DISPUTED` | Proposal 또는 Offer가 `DISPUTED`가 될 때 |
| `DISPUTED -> COMPLETED` | 관리자가 분쟁을 행님 책임으로 판정할 때 |
| `DISPUTED -> FAILED` | 관리자가 분쟁을 꼬붕 책임으로 판정할 때 |
| `STARTED/DISPUTED -> FAILED` | 관리자가 매칭 이후 Proposal을 취소할 때 |
| `COMPLETED -> PAID` | 관리자가 꼬붕 수행비 지급을 기록할 때 |

`PAID`와 `FAILED`는 종료 상태다. 환불 완료로 `FAILED`가 다시 바뀌지는 않는다. 수행비 지급
반려는 기록만 남기고 `COMPLETED`를 유지한다. 지급 관점의 처리 상태(`settlementStatus`)는
`PENDING`, `COMPLETED`, `REJECTED`이며 미션 필드에서 파생한다.

### 세 축 대응

| 단계 | Proposal | Offer | Mission |
|------|----------|-------|---------|
| 매칭 | `MATCHED` | `ACCEPTED` | `STARTED` |
| 한쪽 완료 확인 | `ORDER_COMPLETED` | `RUNNER_COMPLETED` | `STARTED` |
| 양쪽 완료 확인 | `ALL_COMPLETED` | `ALL_COMPLETED` | `COMPLETED` |
| 분쟁 접수 | `DISPUTED` | `DISPUTED` | `DISPUTED` |
| 지급 완료 | `ALL_COMPLETED` | `ALL_COMPLETED` | `PAID` |
| 환불 대상 확정 | `REFUND_PENDING` | `CANCELLED` | `FAILED` |
| 환불 완료 | `REFUNDED` | `CANCELLED` | `FAILED` |

## Refund

Refund는 Proposal의 전액 환불 처리 정본이다. 매칭 전 취소는 Mission 없이 Proposal만
참조하고, 분쟁 또는 관리자 미션 취소 환불은 Mission도 함께 참조한다.

환불 원인은 `USER_CANCELLED`, `ADMIN_CANCELLED`, `DISPUTE_FAILED`, `PAYMENT_EXPIRED` 중
하나이며 상세 문구는 `reasonDetail`로 분리한다.

| reason | 생성 경로 | reasonDetail |
|--------|-----------|--------------|
| `USER_CANCELLED` | 행님이 매칭 전 요청을 취소 | 없음 |
| `ADMIN_CANCELLED` | 관리자가 요청을 취소 | 관리자 취소 메모 |
| `DISPUTE_FAILED` | 관리자가 분쟁을 꼬붕 책임으로 판정 | 사용자가 제출한 분쟁 상세 사유. 기타 사유가 아니면 없을 수 있음 |
| `PAYMENT_EXPIRED` | 입금 마감 24시간이 지나 자동 취소 | 없음 |

### Refund 상태 전이

처리 상태는 `REVIEW`, `PENDING`, `COMPLETED`, `VOIDED`다. `REVIEW`는 환불 의무가 확정되기
이전 단계로, 입금 확인 전 취소된 요청에 실제 입금이 있었는지 관리자가 계좌 내역으로 대조할
때까지 대기한다. `VOIDED`는 대조 결과 입금이 없어 종결한 상태이며, 확정된 환불 의무를
취소하는 반려가 아니다. `PENDING` 이후에는 반려 상태를 두지 않는다.

| 전이 | 발생 시점 |
|------|-----------|
| `(없음) -> REVIEW` | 입금 확인 전(`HOLDING`) 요청이 취소될 때. Proposal은 `CANCELLED`가 된다 |
| `(없음) -> PENDING` | 입금 확인 후 취소 또는 분쟁 실패로 환불 대상이 확정될 때. Proposal은 `REFUND_PENDING`이 된다 |
| `REVIEW -> PENDING` | 관리자가 대조 후 입금을 확인할 때. Proposal은 `CANCELLED`에서 `REFUND_PENDING`으로 되돌아간다 |
| `REVIEW -> VOIDED` | 관리자가 대조 후 입금이 없다고 판단할 때. Proposal은 `CANCELLED`로 남는다 |
| `PENDING -> COMPLETED` | 관리자가 실제 이체 후 환불 완료를 기록할 때. Proposal은 `REFUNDED`가 된다 |

환불은 Proposal당 한 건만 만든다. 같은 Proposal에 대해 다시 요청하면 기존 환불을 재사용한다.

## 정책 기준

- Proposal은 모집 가능 상태에서 Offer를 받을 수 있고, Offer 수락 후 `MATCHED`가 된다.
- Offer 수락 시 선택된 Offer는 `ACCEPTED`, 같은 Proposal의 다른 대기 Offer는 `REJECTED`가 된다.
- 수락된 Offer ID가 매칭 이후 수행 건의 기준 식별자다.
- 매칭 이후 행님 관점 진행 상태는 Proposal, 꼬붕 관점 진행 상태는 Offer에서 추적한다.
- 분쟁 사유 및 선택한 분쟁 설문 질문 ID는 DisputeEvidence에 기록한다. 신고·탈퇴와 같이 사유 선택은 필수이고, `requires_detail`이 `true`인 사유(기타)를 고를 때만 상세 사유가 필수다.
- 공개 모집 상태의 Proposal은 다른 사용자가 신고할 수 있으며, 승인된 신고는 Proposal을 `REPORTED`로 전환하고 대기 Offer를 거절한다.
- 입금 확인 대기(`HOLDING`) Proposal은 `created_at` 기준 24시간이 지나면 자동으로 `CANCELLED`가 된다.
- 입금 확인 전(`HOLDING`) 취소는 Proposal을 바로 `CANCELLED`로 종결하되 `REVIEW` 상태의 Refund를 남긴다. 관리자 입금 확인과 실제 입금 사이에 시차가 있어 취소 시점에는 입금 여부를 알 수 없기 때문이다. 자동 취소도 같다.
- 입금 확인 이후 취소는 항상 `PENDING` Refund를 만들고 `REFUND_PENDING`을 거친다.
- 앱은 `CANCELLED`, `REFUND_PENDING`, `REFUNDED`, `REPORTED`를 모두 취소 배지로 묶어 표시한다.
- 미션 상태는 앱에 노출하지 않는다. 관리자 웹에서만 사용한다.
- 정산 계좌와 약관 동의는 사용자 식별자에 종속된 사용자 부가 정책이다.
