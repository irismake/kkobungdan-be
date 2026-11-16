# Admin/Payment/Settlement Domain

Admin/Payment/Settlement는 관리자 결제 확정, 정산 확정, 분쟁 해결 처리를 담당한다.

## 책임

- 입금 확인 대기 Proposal을 공개 상태로 전환하고 오픈채팅방 링크를 저장한다.
- 생성 후 24시간까지 미입금인 Proposal을 자동 취소하고 행님에게 알린다.
- 요청을 관리자 권한으로 취소한다. 입금 확인 전이면 `CANCELLED`, 입금 확인 후면
  `REFUND_PENDING`으로 종결하고 수행 중이던 Offer와 Mission을 함께 정리한다.
- 입금 확인 전 취소된 요청의 `REVIEW` 환불을 계좌 내역과 대조해, 입금이 있으면 `PENDING`으로
  확정하고 없으면 `VOIDED`로 종결한다.
- 분쟁을 `COMPLETED` 또는 `FAILED`로 판정해 요청·지원·미션을 함께 종결한다. 반려는 없다.
- `COMPLETED` 미션의 꼬붕 수행비 지급을 기록해 `PAID`로 전이하거나 반려 기록만 남긴다.
- 환불은 Refund 정본을 기준으로 목록·상세를 제공하고, 완료 기록 시 Proposal을 `REFUNDED`로
  전이한다.
- 관리자 API는 일반 사용자 수행 상태와 지급·환불 상태를 깨지 않도록 상태 조건을 검증한다.

## 정본 링크

- API 계약: [`../../api-spec/README.md`](../../api-spec/README.md)의 Admin API
- 상태/정책: [`../../domain.md`](../../domain.md)
- 환불 설계 근거: [`../../design-docs/refund-lifecycle.md`](../../design-docs/refund-lifecycle.md)
- 미션 제품 스펙: [`../../product-specs/mission.md`](../../product-specs/mission.md)
- 테스트 보장: [`test-scenarios.md`](./test-scenarios.md)
