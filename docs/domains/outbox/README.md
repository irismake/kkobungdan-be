# Outbox Domain

> 상태: 구현 전

Outbox는 상태 변경과 함께 기록한 이벤트를 발행하고, 전달 대상(consumer)마다 처리·재시도·중복 방지·DEAD 처리·정리를 맡는 공통 모듈이다. 채팅이 처음 쓰고, 이후 결제·환불·정산과 Kafka 도입에 같은 모듈을 쓴다.

## 정본 문서

- 요구사항: [`../../product-specs/event-delivery.md`](../../product-specs/event-delivery.md) (`OUTBOX-REQ-*`)
- 기술 설계: [`../../design-docs/outbox.md`](../../design-docs/outbox.md)
- 테스트 보장 범위: [`test-scenarios.md`](./test-scenarios.md) (`OUTBOX-TS-*`)

## 핵심 개념

- 이벤트 1건은 `outbox_events` 1행, 전달 대상별 처리는 `event_deliveries` 1행이다.
- 발행은 성공할 때까지 재시도하고, 전달은 대상별 정책으로 재시도하다 `DEAD` 또는 `SKIPPED`로 끝난다.
- `DEAD`는 알림을 보내고 관리자가 수동으로 다시 처리한다. 정리 배치는 끝난 이벤트만 7일 뒤 지운다.
