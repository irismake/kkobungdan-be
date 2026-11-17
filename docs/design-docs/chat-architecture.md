# 채팅 아키텍처

> 상태: 설계 확정 (2026-11-17), 구현 전
> 관련 문서: [`../product-specs/chat-requirements.md`](../product-specs/chat-requirements.md) (`CHAT-REQ-*`), [`outbox.md`](./outbox.md) (공통 Transactional Outbox), [`../domains/chat/test-scenarios.md`](../domains/chat/test-scenarios.md) (`CHAT-TS-*`), [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md), [`tdd-workflow.md`](./tdd-workflow.md)

## 배경

카카오톡 오픈채팅방을 앱 내 채팅으로 대체한다. 이 문서는 요구사항(CHAT-REQ-001~029)을 만족하는 서버 구조를 정한다. 특히 아래 요구사항이 구조를 결정한다.

| 요구사항 | 구조에 주는 영향 |
|----------|------------------|
| CHAT-REQ-015~017 실시간 수신, 1초 전달 | 서버가 앱으로 먼저 보내는 연결이 필요하다 → WebSocket |
| CHAT-REQ-019 전송 재시도 중복 방지 | 전송은 응답·재시도가 분명한 REST로 받는다 |
| CHAT-REQ-020·023·026 사건과 채팅방·시스템 채팅의 원자성 | 채팅 갱신은 요청·지원 상태 변경과 같은 DB 트랜잭션에서 한다 |
| CHAT-REQ-024 채팅방별 하나의 저장 순서, 빠짐 없는 복구 | 채팅방마다 순번(`seq`)을 행 잠금 아래에서 매긴다 |
| CHAT-REQ-029 이벤트 전달 보장 (같은 트랜잭션 기록, 재시도, 중복 방지) | MySQL 기반 Transactional Outbox. 이벤트 기록·발행·전달(WebSocket, FCM)을 나눈다 |
| 향후 결제·환불·정산과 함께 Kafka 도입 예정 | 이벤트 봉투와 발행자를 Kafka로 바꿔 끼울 수 있게 둔다. 지금은 Kafka를 구현하지 않는다 |

## 서버 구성

```
 iOS 앱
   │  REST (HTTPS)                         WebSocket (wss, 받기 전용)
   │  - 채팅방 목록·상세·채팅 조회          - 새 채팅, 채팅방 상태, 읽음 위치,
   │  - 채팅 전송, 읽음 처리                  안읽음 수 이벤트
   ▼                                        ▼
 nginx ── /v1/* ───────────────┐   ── /v1/chat/ws (Upgrade, 긴 read timeout) ──┐
                               ▼                                              ▼
 FastAPI 프로세스 (환경당 1개, uvicorn)
   ├ api/v1/chat (REST 라우터)            ├ realtime/ws_router (WebSocket 엔드포인트)
   ├ services/chat (동기, DB 트랜잭션)     ├ realtime/hub (사용자별 연결, 프로세스 메모리)
   │    └ 같은 트랜잭션에서 outbox_events에 이벤트 기록
   ├ outbox 처리 작업 (커밋 직후 바로 + 10초마다) ─ EventPublisher(지금: 프로세스 내, 나중: Kafka)
   │    └ 전달 대상(consumer)별 처리·재시도·중복 방지 (event_deliveries)
   │         ├ ChatRealtimeConsumer → hub ───────┘
   │         └ ChatPushConsumer → FCM (재시도, 10분 지난 푸시는 건너뜀)
   └ 기존 도메인 서비스(offer/proposal/mission/admin/refund/user) ─ 같은 트랜잭션에서 chat lifecycle 직접 호출
                               ▼
                            MySQL
```

### 결정한 것

| 항목 | 결정 | 이유 |
|------|------|------|
| 실시간 수신 | WebSocket. 사용자당 연결 1개(채팅방 단위 아님) | 서버 → 앱 푸시가 필요하고 iOS(`URLSessionWebSocketTask`)가 기본 지원한다 |
| 채팅 전송 | REST `POST`. WebSocket은 받기 전용 | 전송 ID 중복 방지(CHAT-REQ-019), 에러 코드, 테스트가 기존 API와 같아진다 |
| 연결 인증 | `Authorization: Bearer <access token>` 헤더 | 기존 API와 같다. 토큰이 URL과 nginx 접근 로그에 남지 않는다 |
| 프로세스 간 전달 | 프로세스 메모리(`realtime/hub`) | 지금은 환경당 프로세스 1개다. 프로세스를 늘리거나 Kafka를 도입하면 인스턴스마다 이벤트를 받아 자기 연결에 보내는 방식으로 바꾼다 ([`TD-026`](../exec-plans/tech-debt-tracker.md)) |
| 이벤트 전달 | MySQL Transactional Outbox + 전달 대상별 처리 기록 | 변경과 이벤트를 한 트랜잭션에 묶고(CHAT-REQ-029), 서버가 멈춰도 다시 보낼 수 있다. 같은 MySQL을 써서 인프라를 늘리지 않는다 |
| 다른 도메인 → 채팅 연결 | 도메인 서비스가 `ChatLifecycle`을 같은 트랜잭션에서 직접 호출 | 기존 `EventBus`는 핸들러 예외를 삼켜서 "함께 성공·실패"(CHAT-REQ-023·026)를 보장하지 못한다. 기존 `MissionService.sync_from_offer_and_proposal` 직접 호출과 같은 방식이다 |

## 모듈 구성

| 레이어 | 위치 | 책임 |
|--------|------|------|
| API | `app/api/v1/chat/chat_router.py` | 채팅방 목록·상세, 채팅 조회·전송, 읽음·전체 읽음, 안읽음 수 |
| API (관리자) | `app/api/v1/admin/admin_chat_router.py` | 관리자 채팅방 조회·채팅 조회 (읽음 상태를 바꾸지 않음) |
| 실시간 | `app/realtime/ws_router.py`, `app/realtime/hub.py` | WebSocket 인증·연결 등록·ping·토큰 만료 시 종료, 사용자별 이벤트 전송 |
| Service | `app/services/chat/chat_room_service.py` | 채팅방 조회, 참여 권한 확인, 목록 정렬 |
| Service | `app/services/chat/chat_message_service.py` | 일반 채팅 전송(검증·순번·중복 방지), 조회(이전·이후 페이지) |
| Service | `app/services/chat/chat_read_service.py` | 읽음 위치 이동(뒤로만), 전체 읽음, 안읽음 수 계산 |
| Service | `app/services/chat/chat_lifecycle.py` | 다른 도메인이 부르는 입구. 채팅방 생성, 상태·`statusReason` 변경, 시스템 채팅 저장 |
| Service | `app/services/chat/system_chat.py` | 사건별 문구·받는 사람·안읽음·푸시 대상 표 (CHAT-REQ-021) |
| Outbox (공통) | `app/models/outbox.py`, `app/services/outbox/` | 이벤트 기록·발행·전달 처리·재시도·DEAD·재처리·정리. 채팅을 모르는 공통 모듈 ([`outbox.md`](./outbox.md)) |
| Service | `app/services/chat/chat_events.py` | 채팅 이벤트 유형과 내용 정의, `record_event` 호출 도우미 |
| Consumer | `app/services/chat/consumers/realtime_consumer.py` | 채팅 이벤트를 받는 사람을 정해 hub로 보낸다 (WebSocket) |
| Consumer | `app/services/chat/consumers/push_consumer.py` | 채팅 이벤트를 받는 사람·문구·배지로 바꿔 FCM으로 보낸다 |
| Model | `app/models/chat.py` | `ChatRoom`, `ChatMessage`와 상태 enum |
| Schema | `app/schemas/chat.py` | 요청·응답 DTO (`extra="forbid"`, camelCase alias) |

## 의존성 규칙

기존 의존 방향 `api → services → models`(`schemas`는 검증용)를 그대로 따른다.

- 채팅 서비스는 `models`의 User·Proposal·Offer·Mission·Refund를 읽을 수 있다. 다른 도메인의 서비스는 부르지 않는다.
- 다른 도메인 서비스(offer, proposal, mission, admin, refund, user 탈퇴)는 채팅 쪽에서 `chat_lifecycle` 하나만 부른다. `chat_message_service` 등 내부 모듈은 부르지 않는다.
- `chat_lifecycle`은 커밋하지 않는다. 호출한 서비스의 트랜잭션 안에서 변경만 하고, 커밋은 호출한 쪽이 한다.
- 채팅 서비스는 WebSocket·FCM을 직접 부르지 않는다. 보낼 일을 `outbox.writer.record_event`로 기록만 한다(이벤트 발행 로직). 실제 전달은 consumer가 한다(전달 로직).
- consumer는 서비스를 부르지 않고 이벤트 내용과 읽기 전용 조회만으로 전달한다. 전달 실패가 채팅 저장이나 상태 변경을 되돌리지 않는다.
- `outbox` 패키지는 채팅을 모른다. 이벤트 유형 문자열과 내용(JSON)만 다룬다. 그래서 결제·환불·정산 이벤트도 같은 테이블과 relay를 쓸 수 있다.
- `realtime/hub`는 DB를 모른다. 사용자 ID와 이벤트만 받는다.

### `ChatLifecycle` 호출 지점

| 사건 | 호출하는 곳 | 채팅방 변화 | 시스템 채팅 |
|------|-------------|-------------|-------------|
| 지원 등록 | `OfferService.create` | 생성 `ACTIVE` | 지원 등록 안내 → 첫 인사(꼬붕 일반 채팅) |
| 매칭 | `OfferService.accept` | 선택 `ACTIVE`, 나머지 `CLOSED·NOT_SELECTED` | 매칭 확정 / 매칭 미선정 |
| 꼬붕 지원 취소 | `OfferService.cancel` | `CLOSED·OFFER_CANCELLED` | 지원 취소 |
| 꼬붕 탈퇴로 자동 취소 | `UserWithdrawalService.withdraw_user` | `CLOSED·OFFER_CANCELLED` | 지원 취소 |
| 행님 요청 취소(매칭 전) | `ProposalService.cancel` | `CLOSED·PROPOSAL_CANCELLED` | 매칭 전 요청 취소 |
| 관리자 취소 | `AdminCommandService.cancel_proposal` | `CLOSED·ADMIN_CANCELLED` | 임무 유무로 매칭 전/후 문구 |
| 게시글 신고 승인 | `ProposalReportService.accept` | 대기 지원 채팅방 `CLOSED·ADMIN_CANCELLED` | 없음 |
| 꼬붕 임무 완료 / 행님 완료 확인 | `OfferService.complete_delivery` / `ProposalService.confirm_received` | 양측 완료 시 `CLOSED·ALL_CONFIRMED` | 한쪽 완료 / 양측 완료 |
| 분쟁 접수 | `OfferService.raise_dispute` / `ProposalService.raise_dispute` | `INACTIVE·RUNNER_DISPUTED` / `ORDERER_DISPUTED` | 분쟁 접수 |
| 분쟁 판정 | `MissionService.resolve_dispute`, `AdminCommandService.resolve_dispute` | `CLOSED·DISPUTE_COMPLETED` / `DISPUTE_FAILED` | 판정 결과 |
| 수행비 입금 | `MissionService.record_settlement`, `AdminCommandService.complete_payout` (임무 `PAID`) | 없음 | 수행비 입금 완료 |
| 환불 완료 | `AdminCommandService.complete_refund` (Refund `COMPLETED`, 매칭 후만) | 없음 | 환불 완료 |

## 데이터 모델

상태값은 CLAUDE.md 규칙대로 Python Enum + `enum_column`(VARCHAR + 이름 붙인 CHECK)으로 둔다. 다른 테이블처럼 외래 키는 두지 않고 인덱스와 유니크 제약으로 무결성을 지킨다.

### `chat_rooms`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | BIGINT PK | |
| `offer_id` | BIGINT, UNIQUE `uk_chat_rooms_offer_id` | 지원 1건당 채팅방 1개 (CHAT-REQ-001·023) |
| `proposal_id` | BIGINT, INDEX | |
| `orderer_id`, `runner_id` | VARCHAR(36), INDEX | 참여자 2명. 역할을 컬럼으로 고정한다 |
| `status` | VARCHAR(10) CHECK `ck_chat_rooms_status_values` | `ACTIVE`, `INACTIVE`, `CLOSED` |
| `status_reason` | VARCHAR(30) CHECK, NULL | [상태 이유](../product-specs/chat-requirements.md#상태-이유-statusreason) 값 |
| `last_seq` | BIGINT, 기본 0 | 마지막으로 매긴 채팅 순번 |
| `last_message_at` | DATETIME(6), NULL | 목록 정렬용. 채팅이 없으면 `created_at`으로 정렬 |
| `orderer_last_read_seq`, `runner_last_read_seq` | BIGINT, 기본 0 | 참여자별 읽음 위치 |
| `version` | BIGINT, 기본 0 | 상태·읽음 이벤트의 순서 값 (CHAT-REQ-028). 채팅방 상태나 읽음 위치가 바뀔 때마다 1 증가 |
| `created_at`, `updated_at` | DATETIME(6) | UTC |

- 목록 조회: `(orderer_id, last_message_at)`, `(runner_id, last_message_at)` 인덱스로 두 역할을 각각 읽어 합친다.
- 참여자가 2명으로 고정이라 참여자 테이블을 따로 두지 않는다.

### `chat_messages`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | BIGINT PK | 채팅 ID. 앱의 중복 제거 기준 (CHAT-REQ-015·028) |
| `room_id` | BIGINT | |
| `seq` | BIGINT, UNIQUE (`room_id`, `seq`) | 채팅방 안의 저장 순서 (CHAT-REQ-024). 조회·복구·읽음의 기준 |
| `type` | VARCHAR(10) CHECK | `USER`, `SYSTEM` |
| `sender_id` | VARCHAR(36), NULL | 일반 채팅의 보낸 사람. 시스템 채팅은 NULL |
| `content` | TEXT, NULL | 일반 채팅 내용 (화면 글자 500자 이하는 앱 계층에서 검증) |
| `system_event` | VARCHAR(40) CHECK, NULL | 시스템 채팅 사건 코드 (예: `OFFER_CREATED`, `MATCHED`, `NOT_SELECTED`) |
| `system_payload` | JSON, NULL | 문구에 들어갈 값 (예: 수행비 금액) |
| `system_event_key` | VARCHAR(100), NULL, UNIQUE (`room_id`, `system_event_key`) | 같은 사건의 중복 저장 방지 (CHAT-REQ-020). 예: `MISSION_PAID:mission:12` |
| `client_message_id` | VARCHAR(64), NULL, UNIQUE (`sender_id`, `client_message_id`) | 앱 전송 ID. 사용자별 중복 방지 (CHAT-REQ-019) |
| `created_at` | DATETIME(6) | UTC 전송 시각 |

- 시스템 채팅 문구는 저장하지 않고 `system_event` + `system_payload`로 저장한 뒤, 조회할 때 보는 사람(행님/꼬붕)에 맞는 문구로 만든다. 같은 사건은 채팅방마다 한 행이다(CHAT-REQ-020). 문구 표는 `system_chat.py` 한 곳에 둔다.

### Outbox 테이블

`outbox_events`, `event_deliveries`는 공통 모듈의 테이블이다. 구조는 [`outbox.md` 데이터 모델](./outbox.md#데이터-모델)을 따른다.

### 차단

차단 테이블과 API는 [`user-block.md`](../product-specs/user-block.md) 구현 때 만든다. 채팅 쪽은 전송·응답·이벤트에서 "차단 여부 조회" 함수 하나에만 의존하게 두고, 그 전까지는 항상 "차단 없음"을 돌려준다.

## 핵심 처리

### 채팅 전송 (CHAT-REQ-003·019·024·025)

1. 같은 사용자·같은 `client_message_id`가 이미 있으면: 내용과 채팅방이 같으면 그 채팅으로 응답하고 끝낸다. 다르면 `409`.
2. `SELECT … FOR UPDATE`로 `chat_rooms` 행을 잠근다. 채팅방 상태가 `ACTIVE`이고 차단이 없는지 이 잠금 아래에서 확인한다.
3. `last_seq + 1`을 새 채팅의 `seq`로 쓰고, `last_seq`, `last_message_at`, 보낸 사람의 읽음 위치(직전 채팅까지)를 갱신한다.
4. 커밋한다. 커밋 후 상대방에게 실시간 이벤트와 푸시를 보낸다.

- 순번을 채팅방 행 잠금 아래에서 매기므로, 같은 채팅방에서는 커밋 순서와 `seq` 순서가 같다. 그래서 "마지막으로 받은 `seq` 이후" 조회에서 늦게 커밋된 앞 순번 때문에 빠지는 채팅이 없다.
- 채팅방 상태 변경과 시스템 채팅 저장도 같은 행을 잠그므로, 전송과 종료가 겹치면 먼저 잠근 쪽이 확정된다(CHAT-REQ-025). 종료 안내 뒤에 일반 채팅이 저장되지 않는다.
- 동시에 같은 `client_message_id`가 두 번 들어오면 유니크 제약이 하나를 막고, 막힌 쪽은 저장된 채팅을 다시 읽어 응답한다.

### 요청·지원 상태와 함께 바뀌는 처리 (CHAT-REQ-007·020·023·026)

- `ChatLifecycle`은 호출한 서비스의 트랜잭션 안에서 채팅방 행을 잠그고 상태·`statusReason`·`version`을 바꾸고 시스템 채팅을 저장한다. 상태 전이는 `ACTIVE → INACTIVE → CLOSED`, `ACTIVE → CLOSED`만 허용하고, `CLOSED`에서는 바꾸지 않는다(늦게 온 요청 무시).
- 서로 겹치는 동작(매칭과 지원 취소, 매칭과 요청 취소 등)이 하나로만 확정되도록, 해당 서비스들이 상태를 바꾸기 전에 요청(`proposals`) 행을 `SELECT … FOR UPDATE`로 잠그게 바꾼다. 지금은 잠금이 없다([`chat-requirements.md` 기존 기능 영향](../product-specs/chat-requirements.md#기존-기능-영향)).

### 읽음과 안읽음 (CHAT-REQ-010~013·027)

- 읽음 처리는 `UPDATE chat_rooms SET runner_last_read_seq = GREATEST(runner_last_read_seq, :seq)`처럼 한 문장으로 한다. 동시에 들어와도 뒤로 돌아가지 않는다.
- 요청한 `seq`가 그 채팅방의 `last_seq`보다 크면 거부한다(없는 채팅).
- 안읽음 수는 저장하지 않고 계산한다: 내 읽음 위치보다 큰 `seq` 중 상대가 보낸 일반 채팅 + 나에게 보이는 시스템 채팅(행님 기준 `NOT_SELECTED` 제외). `(room_id, seq)` 인덱스로 센다.
- 전체 읽음은 요청 시점의 각 채팅방 `last_seq`까지 같은 방식으로 올린다.

### 실시간 (CHAT-REQ-015~017·028)

- 엔드포인트: `GET /v1/chat/ws` (WebSocket). `Authorization` 헤더의 access token을 검증하고 연결을 받는다. 토큰이 만료되면 연결을 거부하고, 연결 중 만료 시각이 되면 서버가 닫는다(close code `4401`).
- 서버는 30초마다 ping을 보낸다. 앱은 받기만 한다.
- 이벤트 (JSON, `type`으로 구분):

| type | 받는 사람 | 내용 |
|------|-----------|------|
| `chat.message.created` | 두 참여자 | 채팅 ID, 채팅방 ID, `seq`, 유형, 보는 사람 기준 내용, 시각 |
| `chat.room.updated` | 두 참여자 | 채팅방 상태, `statusReason`, 요청·지원 상태, 완료 확인 여부, `version` |
| `chat.read.updated` | 상대방 | 읽은 사람의 마지막 읽은 `seq`, `version` |
| `chat.unread.updated` | 본인 | 채팅방 안읽음 수, 전체 합계 |

- 끊긴 동안 놓친 것은 REST로 복구한다: 채팅방별 `afterSeq` 조회, 채팅방 목록, 상세(읽음 위치·상태).
- 실시간 이벤트는 서비스가 outbox에 기록하고, `ChatRealtimeConsumer`가 받는 사람을 정해 hub로 보낸다. 동기 코드(relay 스레드)에서 hub로 넘길 때는 hub가 가진 이벤트 루프에 `call_soon_threadsafe`로 넘긴다.
- 받는 사람이 연결되어 있지 않으면 보낼 곳이 없을 뿐 실패가 아니다. 실시간 전달은 다시 시도하지 않는다. 늦게 보낸 실시간 이벤트는 의미가 없고, 앱은 재연결 때 REST로 복구한다.

### 푸시 (CHAT-REQ-018)

- 서비스가 outbox에 기록한 이벤트를 `ChatPushConsumer`가 FCM으로 보낸다. `notifications`에는 저장하지 않는다.
- 실패하면 최대 5회 다시 시도하고, 채팅 저장 후 10분이 지났으면 보내지 않고 `SKIPPED`로 끝낸다(아래 [채팅 전달 대상](#채팅-전달-대상)).
- 제목은 상대방 이름(탈퇴는 `"탈퇴한 사용자"`), 내용은 받는 사람에게 보이는 채팅 문구.
- 같은 채팅방 푸시는 묶는다: APNs `apns-collapse-id`와 Android `tag`를 `chat-room-{id}`로 둔다.
- 배지는 채팅 안읽음 합계 + 알림 미읽음 수. 기존 알림 푸시도 같은 값을 보내도록 `fcm_service`의 고정값 `badge=1`을 바꾼다.
- 시스템 채팅의 푸시 대상은 `system_chat.py` 표를 따른다(기존 알림을 받는 사람 제외).

## 이벤트 전달 (Transactional Outbox)

채팅은 공통 [Transactional Outbox](./outbox.md)와 정책 [`event-delivery.md`](../product-specs/event-delivery.md)(`OUTBOX-REQ-*`)를 따른다. 여기에는 채팅에만 해당하는 것만 적는다.

### 채팅 이벤트

모두 `aggregate_type = chat_room`, `aggregate_id = 채팅방 ID`로 기록한다. 같은 채팅방 이벤트는 기록 순서대로 발행·전달된다.

| 이벤트 유형 | 기록하는 곳 | 내용 |
|-------------|-------------|------|
| `chat.message.created` | 채팅 전송, 시스템 채팅 저장 | 채팅 ID, `seq`, 유형, 보낸 사람, 시스템 사건 코드·값 |
| `chat.room.updated` | 채팅방 상태 변경, 요청·지원 상태·완료 확인 변경 | 상태, `statusReason`, 요청·지원 상태, 완료 확인 여부, `version` |
| `chat.read.updated` | 읽음, 전체 읽음 | 읽은 사람, 마지막 읽은 `seq`, `version` |

안읽음 수 이벤트(`chat.unread.updated`)는 따로 기록하지 않고, `chat.realtime`이 위 이벤트를 보낼 때 받는 사람의 안읽음 수를 계산해 함께 보낸다.

### 채팅 전달 대상

| 전달 대상 | 받는 이벤트 | 하는 일 | 재시도 정책 |
|-----------|-------------|---------|-------------|
| `chat.realtime` | 세 가지 모두 | 받는 사람을 정해 hub로 WebSocket 전송 | 재시도 없음. 연결이 없거나 전송 오류면 `SKIPPED`. 앱은 재연결 후 REST로 복구 (CHAT-REQ-016) |
| `chat.push` | `chat.message.created` | 받는 사람·문구·배지를 정해 FCM 전송. 기존 알림을 받는 사람·보낸 사람 본인·알림 꺼짐은 `SKIPPED` | 최대 5회, 5초·30초·1분·2분·4분, 유효 10분. 초과 시 `DEAD` + 알림 |

- `chat.push`는 같은 채팅방 푸시를 FCM 묶음 키(`chat-room-{id}`)로 대체하므로, 결과 기록 전 중단으로 한 번 더 보내도 사용자에게는 하나로 보인다(멱등).
- `chat.realtime`은 앱이 채팅 ID와 `version`으로 중복을 거른다(CHAT-REQ-028).
- relay·전달 처리는 같은 프로세스에서 돌고, `chat.realtime`은 그 프로세스의 hub로 보낸다. Kafka 도입 뒤 인스턴스별 consumer group으로 바꾸는 것은 [`outbox.md` Kafka 도입 시](./outbox.md#kafka-도입-시-지금은-구현하지-않음)를 따른다 (TD-026).

## API (초안)

정본은 구현하면서 [`../api-spec/README.md`](../api-spec/README.md)에 적는다. 경로는 기존 단수형 규칙(`/v1/offer`)을 따른다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/v1/chat-room` | 내 채팅방 목록 (마지막 채팅 최신순, 커서 페이지) |
| GET | `/v1/chat-room/unread-count` | 채팅방별 안읽음 수와 합계 |
| POST | `/v1/chat-room/read-all` | 전체 읽음 |
| GET | `/v1/chat-room/{roomId}` | 채팅방 상세 (상태, 상대, 요청·지원 상태, 내·상대 읽음 위치) |
| GET | `/v1/chat-room/{roomId}/messages?beforeSeq=&size=30` | 이전 채팅 (처음은 최근 30개) |
| GET | `/v1/chat-room/{roomId}/messages?afterSeq=` | 놓친 채팅 복구 |
| POST | `/v1/chat-room/{roomId}/messages` | 채팅 전송 `{clientMessageId, content}` |
| POST | `/v1/chat-room/{roomId}/read` | 읽음 `{seq}` |
| POST | `/v1/offer` (변경) | 첫 인사 `greeting` 필수 추가 |
| GET | `/v1/admin/chat-room?proposalId=` | 관리자 채팅방 조회 |
| GET | `/v1/admin/chat-room/{roomId}/messages` | 관리자 채팅 조회 |
| WS | `/v1/chat/ws` | 실시간 이벤트 |

에러 코드는 기존 카탈로그(`app/core/errors.py`)에 추가하고 문구는 [`error-copy-policy.md`](../product-specs/error-copy-policy.md)를 따른다. 예: `CHAT_ROOM_NOT_FOUND`(404), `CHAT_ROOM_ACCESS_DENIED`(403), `CHAT_ROOM_NOT_SENDABLE`(409, `INACTIVE`·`CLOSED`·차단), `CHAT_MESSAGE_ID_CONFLICT`(409), `CHAT_READ_SEQ_INVALID`(400).

## 배포·운영 변경

- nginx: 운영·staging 서버 블록에 `/v1/chat/ws` location을 추가한다(`Upgrade`·`Connection` 헤더, `proxy_read_timeout` 3600s).
- 기존 지원 채팅방 생성: Alembic 데이터 마이그레이션으로 채팅방이 없는 지원마다 채팅방을 만든다. 상태는 지원 상태로 정하고 시스템 채팅은 만들지 않는다(CHAT-REQ-023). 이미 있으면 건너뛴다.
- uvicorn은 지금처럼 프로세스 1개로 둔다. `--workers`를 늘리면 실시간 전달이 깨진다([`TD-026`](../exec-plans/tech-debt-tracker.md)).

## 대안과 결정

| 대안 | 장점 | 단점 | 결정 |
|------|------|------|------|
| SSE | 단방향이라 단순하다 | iOS 기본 지원이 없다 | 채택하지 않음 |
| 폴링 | 가장 단순하다 | 1초 전달을 지키려면 요청이 매우 많다 | 채택하지 않음 |
| WebSocket으로 전송까지 | 왕복이 조금 빠르다 | 응답·재시도·에러를 따로 만들어야 한다 | 채택하지 않음. 전송은 REST |
| Redis Pub/Sub부터 | 프로세스를 늘려도 동작한다 | t3.micro에 Redis를 더 올려야 한다 | 채택하지 않음. 확장은 Kafka 도입 때 인스턴스별 consumer group으로 한다 (TD-026) |
| 토큰을 URL 쿼리로 | 가장 간단하다 | nginx 로그에 토큰이 남는다 | 채택하지 않음 |
| `EventBus` 구독으로 채팅 갱신 | 도메인 간 결합이 약하다 | 핸들러 예외를 삼켜 원자성을 깨뜨린다 | 채택하지 않음. `ChatLifecycle` 직접 호출 |
| `chat_messages.id`(auto increment)를 순서로 사용 | 컬럼이 하나 준다 | 커밋 순서와 id 순서가 달라 복구 때 빠지는 채팅이 생길 수 있다 | 채택하지 않음. 채팅방별 `seq` |
| 시스템 채팅 문구를 받는 사람별로 저장 | 조회가 단순하다 | 같은 사건이 두 행이 되고 문구 변경이 어렵다 | 채택하지 않음. 사건 코드 저장 후 조회 시 문구 생성 |
| 안읽음 수를 카운터 컬럼으로 저장 | 조회가 빠르다 | 동시성에서 정의와 어긋나기 쉽다 (CHAT-REQ-027) | 채택하지 않음. 읽음 위치로 계산 |
| 커밋 후 메모리에서 바로 전달 (`after_commit`) | 테이블이 필요 없다 | 커밋 직후 서버가 멈추면 이벤트를 잃고, 재시도할 근거가 없다 | 채택하지 않음 (2026-11-17 공통 Outbox로 변경, [`outbox.md`](./outbox.md)) |
| 처음부터 Kafka | 확장성이 가장 좋다 | 지금 필요한 규모가 아니고, 별도 서버가 아직 없다 | 채택하지 않음. 발행자 인터페이스와 이벤트 봉투만 맞춰 둔다 |

## 리스크와 후속 작업

- 프로세스 메모리 hub라 서버를 2개 이상으로 늘리면 실시간 전달이 깨진다 (TD-026). Kafka 도입 때 인스턴스별 consumer group으로 해결한다.
- Outbox 공통 리스크(주기 조회 부하, at-least-once)는 [`outbox.md` 리스크](./outbox.md#리스크)를 따른다.
- 배포로 앱이 재시작되면 모든 WebSocket이 끊긴다. 앱은 재연결 후 REST로 복구한다(CHAT-REQ-016).
- 기존 상태 변경 서비스에 요청 행 잠금을 넣으면 처리 순서가 바뀔 수 있다. 기존 통합 테스트로 회귀를 확인한다.
- 사용자 차단, 채팅 신고, 사진 전송, 보관 기한은 이 설계 밖이다.

## 구현 순서

[`../exec-plans/active/2026-11-17-chat-implementation.md`](../exec-plans/active/2026-11-17-chat-implementation.md)를 따른다.
