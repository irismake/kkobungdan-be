# Outbox Test Scenarios

> 상태: 구현됨 (모든 시나리오가 테스트에 연결됨)
> 요구사항 정본: [`event-delivery.md`](../../product-specs/event-delivery.md) (`OUTBOX-REQ-*`)

기준 테스트 파일: `tests/test_outbox_service.py`(단위), `tests/test_outbox_integration.py`(통합)

## 시나리오

각 시나리오는 테스트와 1:1로 연결한다. 연결 방식은 [`../../design-docs/tdd-workflow.md`](../../design-docs/tdd-workflow.md)를 따른다.

- 테스트 위치 약어: `service` = `tests/test_outbox_service.py`(단위, 가짜 발행자·전달 대상·시계 사용), `api` = `tests/test_outbox_integration.py`(통합, MySQL)
- 실제 업무 이벤트 대신 테스트용 이벤트 유형과 테스트용 전달 대상을 등록해 확인한다. 채팅 전달 대상(`chat.realtime`, `chat.push`) 규칙은 [`../chat/test-scenarios.md`](../chat/test-scenarios.md)에서 확인한다.
- 모니터링 알림은 기존 관리자 Slack 알림의 가짜 발송기로 확인한다.
- 원래 채팅 문서에 있던 공통 시나리오(CHAT-TS-102~104, 107~109)는 이 문서로 옮겼다.

| ID | 요구사항 | 시나리오 (Given / When / Then) | 종류 | 테스트 위치 |
|----|----------|-------------------------------|------|-------------|
| OUTBOX-TS-001 | OUTBOX-REQ-001 | Given 상태 변경과 이벤트 기록을 같은 세션에서 함 / When 커밋, 또는 롤백 / Then 커밋하면 이벤트 1개가 미발행으로 남고, 롤백하면 상태 변경과 이벤트 모두 없다 | integration | `api` |
| OUTBOX-TS-002 | OUTBOX-REQ-002 | Given 커밋 후 바로 발행하지 못한 이벤트(서버 중단 가정) / When 주기 발행 작업이 실행됨 / Then 남은 이벤트가 기록 순서대로 발행되고 발행 완료로 표시된다 | integration | `api` |
| OUTBOX-TS-003 | OUTBOX-REQ-002 | Given 계속 실패하는 발행자 / When 발행 작업이 반복됨 / Then 시도 간격이 5초, 30초, 2분, 10분으로 늘고 그 뒤로 10분을 넘지 않으며, 이벤트는 지워지거나 포기되지 않는다. 발행자가 회복되면 발행된다 | unit | `service` |
| OUTBOX-TS-004 | OUTBOX-REQ-002 | Given 미발행 이벤트 5개 / When 발행 작업 두 개가 동시에 실행됨 **(동시)** / Then 각 이벤트는 정확히 한 번 발행된다 | integration | `api` |
| OUTBOX-TS-005 | OUTBOX-REQ-002 | Given 같은 대상에 이벤트 3개가 기록됨 / When 발행 작업이 처리 / Then 발행자에 기록 순서대로 넘어간다 | unit | `service` |
| OUTBOX-TS-006 | OUTBOX-REQ-008 | Given 이벤트 / When 발행자에 넘길 메시지를 만듦 / Then 이벤트 ID, 유형, 대상 종류, 대상 ID, 스키마 버전, 발생 시각, 내용이 담기고 대상 ID가 순서 키다 | unit | `service` |
| OUTBOX-TS-007 | OUTBOX-REQ-003 | Given 기록된 지 5분이 넘은 미발행 이벤트 / When 지연 점검이 10분 동안 여러 번 실행된 뒤 지연이 풀림 / Then 지연 알림은 1번, 해소 알림은 1번 나간다. 4분 지난 이벤트만 있으면 알림이 없다 | unit | `service` |
| OUTBOX-TS-008 | OUTBOX-REQ-004 | Given 전달 대상 A·B가 받는 이벤트, B만 실패 / When 재시도 처리 / Then A는 `SUCCEEDED`로 남아 다시 처리되지 않고 B만 다시 시도된다 | integration | `api` |
| OUTBOX-TS-009 | OUTBOX-REQ-004 | Given 이미 `SUCCEEDED`·`SKIPPED`·`DEAD`인 전달 / When 같은 이벤트가 같은 전달 대상에 다시 들어옴 / Then 처리하지 않고 건너뛴다 | unit | `service` |
| OUTBOX-TS-010 | OUTBOX-REQ-004 | Given 한 작업이 처리 중(`PROCESSING`)인 전달 / When 다른 작업이 같은 전달을 집으려 함, 그리고 처리하던 작업이 멈춘 뒤 5분이 지남 / Then 처리 중에는 집지 못하고, 5분이 지나면 다시 집어 처리한다 | integration | `api` |
| OUTBOX-TS-011 | OUTBOX-REQ-005 | Given 기본 정책의 전달 대상이 계속 실패 / When 재시도가 반복됨 / Then 간격이 5초, 30초, 2분, 10분, 10분으로 늘고 5회 재시도 후 `DEAD`가 되어 더 시도하지 않는다 | unit | `service` |
| OUTBOX-TS-012 | OUTBOX-REQ-005 | Given 유효 시간이 10분인 전달 대상의 실패한 전달 / When 이벤트 발생 10분 뒤 재시도 / Then 처리하지 않고 `SKIPPED`로 끝낸다 | unit | `service` |
| OUTBOX-TS-013 | OUTBOX-REQ-006 | Given 마지막 재시도도 실패한 전달 / When `DEAD`가 됨 / Then 오류 로그와 모니터링 알림이 1번 나가고, 이후 점검에서 같은 전달로 다시 알리지 않는다 | unit | `service` |
| OUTBOX-TS-014 | OUTBOX-REQ-006 | Given 전달 대상이 다른 `DEAD` 전달 여러 개 / When 관리자가 전달 대상·기간으로 `DEAD` 목록 조회 / Then 조건에 맞는 전달만 이벤트 유형·대상 ID·오류·시도 횟수와 함께 나온다 | integration | `api` |
| OUTBOX-TS-015 | OUTBOX-REQ-006 | Given `DEAD` 전달 / When 관리자가 재처리 요청 / Then 재시도 횟수를 새로 세어 다시 처리되고, 재처리 횟수와 요청한 관리자가 남는다. 처리 성공 시 `SUCCEEDED`다 | integration | `api` |
| OUTBOX-TS-016 | OUTBOX-REQ-006 | Given `SUCCEEDED`·`SKIPPED`·`PROCESSING` 전달 / When 관리자가 재처리 요청 / Then 거부되고 전달은 바뀌지 않는다 | integration | `api` |
| OUTBOX-TS-017 | OUTBOX-REQ-006 | Given `DEAD` 전달 / When 관리자 재처리 요청 두 개가 동시에 들어옴 **(동시)** / Then 한 번만 다시 처리되고 재처리 횟수는 1 늘어난다 | integration | `api` |
| OUTBOX-TS-018 | OUTBOX-REQ-006 | Given 같은 전달 대상의 `DEAD` 전달 3개와 다른 대상의 `DEAD` 1개 / When 관리자가 전달 대상 단위로 일괄 재처리 / Then 그 대상의 3개만 다시 처리된다 | integration | `api` |
| OUTBOX-TS-019 | OUTBOX-REQ-006 | Given 유효 시간이 지난 `DEAD` 전달 / When 관리자가 재처리 요청 / Then 처리하지 않고 `SKIPPED`로 끝난다 | unit | `service` |
| OUTBOX-TS-020 | OUTBOX-REQ-006 | Given 관리자가 아닌 사용자 / When `DEAD` 목록 조회나 재처리 요청 / Then 기존 관리자 API와 같이 거부된다 | integration | `api` |
| OUTBOX-TS-021 | OUTBOX-REQ-007 | Given 모든 전달이 `SUCCEEDED`·`SKIPPED`이고 끝난 지 8일 된 이벤트, 6일 된 이벤트, `DEAD`가 있는 이벤트, `FAILED`가 있는 이벤트, 미발행 이벤트 / When 정리 작업 실행 / Then 8일 된 이벤트와 그 전달 기록만 지워지고 나머지는 모두 남는다 | integration | `api` |
