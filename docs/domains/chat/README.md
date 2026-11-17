# Chat Domain

> 상태: 구현 전

ChatRoom(채팅방)은 지원(Offer) 1건마다 만들어지는 행님과 꼬붕의 1:1 대화 공간이다. 채팅방에는 참여자가 보낸 일반 채팅과 서버가 요청·지원·임무 사건에 맞춰 남기는 시스템 채팅이 저장 순서대로 쌓인다.

## 정본 문서

- 요구사항: [`../../product-specs/chat-requirements.md`](../../product-specs/chat-requirements.md) (`CHAT-REQ-*`)
- 기술 설계: [`../../design-docs/chat-architecture.md`](../../design-docs/chat-architecture.md)
- 차단 정책: [`../../product-specs/user-block.md`](../../product-specs/user-block.md)
- 채팅 신고: [`../../product-specs/chat-reporting.md`](../../product-specs/chat-reporting.md)
- 테스트 보장 범위: [`test-scenarios.md`](./test-scenarios.md) (`CHAT-TS-*`)

## 핵심 개념

- 채팅방 상태(`ACTIVE`, `INACTIVE`, `CLOSED`)와 `statusReason`은 채팅 전송 가능 여부만 나타내며 요청·지원 상태 변화로만 바뀐다.
- 읽음은 참여자별 마지막 읽은 채팅으로 기록하고, 안읽음 수는 그 위치에서 계산한다.
- 채팅 푸시는 `notifications`에 저장하지 않는다. 실시간 이벤트와 푸시는 Transactional Outbox(`outbox_events`)로 같은 트랜잭션에 기록한 뒤 전달 대상별로 보내고, 실패하면 재시도한다.
