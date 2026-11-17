# Transactional Outbox

> 상태: 구현됨 (2026-11-17, 0036_create_outbox_tables)
> 관련 문서: [`../product-specs/event-delivery.md`](../product-specs/event-delivery.md) (`OUTBOX-REQ-*`), [`../domains/outbox/test-scenarios.md`](../domains/outbox/test-scenarios.md) (`OUTBOX-TS-*`), [`chat-architecture.md`](./chat-architecture.md) (첫 사용처)

## 배경

상태 변경 뒤에 다른 곳으로 알려야 하는 일을 잃지 않고, 실패하면 다시 시도하고, 두 번 처리하지 않기 위한 공통 모듈이다. 채팅의 실시간 이벤트·푸시에 먼저 쓰고, 이후 PG 결제·환불·정산 이벤트와 Kafka 도입에 같은 모듈과 정책을 쓴다. Kafka는 지금 구현하지 않고, 별도 서버(라즈베리파이)에 둘 예정이다.

## 구성

```
 도메인 서비스 트랜잭션
   상태 변경 + record_event() ──▶ outbox_events (미발행)        OUTBOX-REQ-001
   COMMIT
        │ 커밋 직후 깨움 + 10초 처리 작업
        ▼
 relay: 미발행을 id 순으로 집음 (FOR UPDATE SKIP LOCKED)        OUTBOX-REQ-002
   └ EventPublisher.publish(envelope)   지금: InProcessEventPublisher / 나중: KafkaEventPublisher
        ├ 성공 → published_at 기록
        └ 실패 → 5초·30초·2분·10분, 이후 10분마다 (포기 안 함)
        ▼
 전달(delivery) 처리: 이벤트를 받는 전달 대상마다 event_deliveries 1행    OUTBOX-REQ-004·005
   PENDING ─집음─▶ PROCESSING(5분 임대) ─┬▶ SUCCEEDED
                                         ├▶ SKIPPED  (처리할 필요 없음 / 유효 시간 지남)
                                         ├▶ FAILED ─(다음 시도 시각)─▶ PROCESSING …
                                         └▶ DEAD     (최대 재시도 초과) ─▶ 알림     OUTBOX-REQ-006
 관리자 재처리: DEAD ─(조건부 전이)─▶ PENDING
 주기 작업: 처리 작업(10초: 발행 → 전달·재시도 → 지연 점검) · 정리(매일 04:00)   OUTBOX-REQ-003·007
```

## 모듈 구성

`app/services/outbox/`는 업무 도메인을 모른다. 이벤트 유형 문자열과 내용(JSON)만 다룬다.

| 위치 | 책임 |
|------|------|
| `app/models/outbox.py` | `OutboxEvent`, `EventDelivery`, `DeliveryStatus` enum |
| `app/services/outbox/writer.py` | `record_event(db, event_type, aggregate_type, aggregate_id, payload)`. 호출한 세션에 1행 추가, 커밋하지 않음 |
| `app/services/outbox/envelope.py` | `EventEnvelope`(이벤트 봉투) 정의와 직렬화 |
| `app/services/outbox/publisher.py` | `EventPublisher` 인터페이스, `InProcessEventPublisher` |
| `app/services/outbox/relay.py` | 미발행 이벤트 발행, 발행 재시도, 커밋 직후 깨우기 |
| `app/services/outbox/consumers.py` | `EventConsumer` 인터페이스, `RetryPolicy`, 전달 대상 등록(어떤 이벤트 유형을 어떤 대상이 받는지) |
| `app/services/outbox/delivery.py` | 전달 처리: 행 확보·집기(임대)·상태 전이·재시도 일정·DEAD·SKIPPED |
| `app/services/outbox/monitor.py` | 발행 지연 점검, DEAD 알림 (기존 관리자 Slack 알림 `AdminAlertSender` 사용) |
| `app/services/outbox/admin.py` | DEAD 목록 조회, 단건·일괄 재처리 |
| `app/services/outbox/cleanup.py` | 정리 배치 |
| `app/api/v1/admin/admin_outbox_router.py` | 관리자 API |

도메인(채팅, 이후 결제·정산)은 아래만 만든다.

- 이벤트 유형과 내용 정의, `record_event` 호출
- `EventConsumer` 구현과 `RetryPolicy`
- [`event-delivery.md` 전달 대상별 정책](../product-specs/event-delivery.md#전달-대상별-정책-현재) 표에 한 줄 추가

## 데이터 모델

상태값은 CLAUDE.md 규칙대로 Python Enum + `enum_column`(VARCHAR + 이름 붙인 CHECK)이다.

### `outbox_events`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | BIGINT PK | 기록 순서. 발행 순서 |
| `event_id` | VARCHAR(36), UNIQUE | 이벤트 ID(UUID). 전달 중복 방지 키 |
| `event_type` | VARCHAR(60) | 예: `chat.message.created`, 이후 `payment.approved` |
| `aggregate_type` | VARCHAR(30) | 예: `chat_room`, `payment`. Kafka 토픽 선택 기준 |
| `aggregate_id` | VARCHAR(64) | 순서 키. Kafka 파티션 키 |
| `schema_version` | SMALLINT | 내용 형식 버전 |
| `payload` | JSON | 이벤트 내용 |
| `occurred_at` | DATETIME | 사건 시각(UTC). 유효 시간 계산 기준 |
| `published_at` | DATETIME, NULL | 발행 완료 시각. NULL이면 미발행 |
| `publish_attempts` | INT, 기본 0 | 발행 시도 횟수 |
| `next_publish_at` | DATETIME, NULL | 발행 실패 후 다음 시도 시각 |
| `last_publish_error` | VARCHAR(500), NULL | |

- 인덱스: (`published_at`, `next_publish_at`, `id`)로 발행할 이벤트를 순서대로 꺼낸다. 발행 지연 점검은 미발행 중 가장 작은 `id`의 `occurred_at`을 본다.

### `event_deliveries`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | BIGINT PK | |
| `event_id` | VARCHAR(36) | |
| `consumer` | VARCHAR(50) | 예: `chat.realtime`, `chat.push`. Kafka consumer group에 대응 |
| `status` | VARCHAR(12) CHECK | `PENDING`, `PROCESSING`, `SUCCEEDED`, `FAILED`, `SKIPPED`, `DEAD` |
| `attempts` | INT, 기본 0 | 이번 회차의 시도 횟수. 수동 재처리 때 0으로 되돌린다 |
| `next_attempt_at` | DATETIME, NULL | `FAILED`일 때 다음 시도 시각 |
| `locked_until` | DATETIME, NULL | `PROCESSING` 임대 만료 시각(집은 뒤 5분) |
| `last_error` | VARCHAR(500), NULL | |
| `skip_reason` | VARCHAR(50), NULL | `SKIPPED` 이유 (예: `expired`, `not_connected`) |
| `dead_alerted_at` | DATETIME, NULL | DEAD 알림을 보낸 시각. 한 번만 알리기 위함 |
| `manual_retry_count` | INT, 기본 0 | 수동 재처리 횟수 |
| `last_manual_retry_by` | VARVARCHAR(36), NULL | 마지막 재처리를 요청한 관리자 |
| `finished_at` | DATETIME, NULL | `SUCCEEDED`·`SKIPPED`·`DEAD`가 된 시각. 정리 기준 |
| `created_at`, `updated_at` | DATETIME | |

- UNIQUE (`event_id`, `consumer`): 같은 이벤트를 같은 전달 대상이 두 번 처리하지 않는다. Kafka를 도입해도 같은 메시지가 다시 올 수 있으므로(at-least-once) 이 테이블이 중복 방지(inbox) 역할을 그대로 한다.
- 인덱스: (`status`, `next_attempt_at`), (`status`, `locked_until`), (`consumer`, `status`, `finished_at`).

## 주기 작업

앱 프로세스의 APScheduler에 두 작업만 등록한다(`app/services/outbox/worker.py` `register_outbox_jobs`). `OUTBOX_WORKER_ENABLED=false`면 등록하지 않는다(테스트).

| 작업 | 언제 | 하는 일 |
|------|------|---------|
| `outbox_cycle` | 10초마다, 그리고 이벤트를 기록한 트랜잭션이 커밋되면 바로 한 번(`outbox_cycle_now`) | ① 미발행 이벤트를 모두 발행 ② 처리할 전달(새 전달, 재시도 시각이 된 `FAILED`, 임대가 끝난 `PROCESSING`)을 더 집을 것이 없을 때까지 처리(최대 20번 반복) ③ 발행 지연 점검 |
| `outbox_cleanup` | 매일 04:00 | 끝난 지 7일 지난 이벤트 삭제 |

- 정상 채팅은 커밋 직후 실행으로 바로 전달된다. 10초 주기는 깨우기를 놓쳤거나(서버 재시작 등) 재시도 시각이 된 전달을 처리하는 안전망이다.
- 순서를 지키려고 한 번에 같은 대상(채팅방 등)의 전달은 하나만 집는다. 그래서 ②를 반복해, 한 트랜잭션에서 생긴 이벤트 여러 개(예: 지원 등록 안내 + 첫 인사)가 다음 주기까지 밀리지 않고 바로 이어서 전달되게 한다.
- 처리 작업은 프로세스 안 잠금으로 한 번에 하나만 돈다. 커밋 직후 실행과 10초 주기가 겹치면 뒤에 온 실행은 바로 끝난다.
- 재시도 횟수·간격(정책 값)과 중복 방지 규칙은 주기와 관계없이 그대로다.

## 처리 규칙

### 기록 (OUTBOX-REQ-001)

- `record_event`는 호출한 세션에 `outbox_events` 1행을 추가만 한다. 커밋·플러시를 하지 않는다.
- 같은 세션에 이벤트가 기록되면 세션 정보에 표시해 두고, SQLAlchemy `after_commit`에서 relay를 깨운다. 롤백되면 표시만 지운다. 깨우기는 빨리 보내기 위한 장치이고(정상 채팅은 이 경로로 바로 전달된다), 놓쳐도 10초 처리 작업이 집는다.

### 발행 (OUTBOX-REQ-002·003)

- relay는 `published_at IS NULL AND (next_publish_at IS NULL OR next_publish_at <= now)`인 이벤트를 `id` 순으로 `FOR UPDATE SKIP LOCKED`로 집어, 발행자에 넘기고 `published_at`을 기록한다. 같은 이벤트를 두 relay가 집지 않는다.
- 같은 대상(`aggregate_id`)의 앞선 이벤트가 발행 실패로 기다리는 중이면 그 대상의 뒤 이벤트도 발행하지 않는다. 순서가 뒤바뀌지 않게 하기 위해서다.
- 발행 실패: `publish_attempts` 증가, `next_publish_at` = 5초 → 30초 → 2분 → 10분, 이후 10분. 포기하지 않는다.
- 발행 지연 점검(10초 처리 작업의 마지막 단계): 가장 오래된 미발행 이벤트가 5분을 넘으면 알림. 같은 지연이 이어지면 30분에 한 번만 다시 알리고, 풀리면 해소 알림 1번. 알림 상태는 프로세스 메모리에 둔다(재시작하면 다시 한 번 알릴 수 있다).
- `InProcessEventPublisher.publish`는 받는 전달 대상마다 `event_deliveries` 행을 `PENDING`으로 만든다(이미 있으면 두지 않음). 실제 처리는 아래 전달 처리 단계가 한다. 그래서 "발행 완료"는 "전달할 일이 기록됨"을 뜻하고, 전달 실패는 발행을 되돌리지 않는다.

### 전달 처리 (OUTBOX-REQ-004·005)

- 집기: `status = PENDING`, 또는 `FAILED`이고 `next_attempt_at`이 지남, 또는 `PROCESSING`이고 `locked_until`이 지남(처리하던 작업이 멈춤). 이 행을 `FOR UPDATE SKIP LOCKED`로 잡아 `PROCESSING`, `locked_until = now + 5분`으로 바꾸고 커밋한 뒤 처리한다.
- 처리 전에 유효 시간을 본다. `occurred_at + 유효 시간`이 지났으면 처리하지 않고 `SKIPPED(expired)`.
- `consumer.handle(envelope)` 결과:
  - 정상 → `SUCCEEDED`
  - `SkipDelivery(reason)` → `SKIPPED(reason)` (처리할 필요 없음)
  - 예외 → `attempts`가 최대 재시도 이하이면 `FAILED`, `next_attempt_at` = 정책 간격. 넘으면 `DEAD`.
- 같은 이벤트 순서: 같은 전달 대상·같은 `aggregate_id`에 앞선 전달이 `PENDING`·`PROCESSING`·`FAILED`이면 뒤 전달은 기다린다. 재시도 중에도 순서가 바뀌지 않는다. (`DEAD`·`SKIPPED`는 끝난 것으로 보고 뒤를 막지 않는다.)
- 결과 기록 전에 서버가 멈추면 임대가 끝난 뒤 다시 처리된다. 그래서 전달 대상은 멱등해야 한다(OUTBOX-REQ-004). 채팅 푸시는 FCM 묶음 키로 같은 채팅방 푸시를 대체해 사용자에게 두 번 보이지 않고, 결제·정산은 업무 키로 이미 처리했는지 확인한다.

### 재시도 정책

```python
@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int                      # 0이면 재시도 안 함 (실패 시 처리 방식은 consumer가 SkipDelivery로 정함)
    backoff: tuple[timedelta, ...]         # n번째 재시도 간격. 길이를 넘으면 마지막 값을 반복
    expires_after: timedelta | None        # occurred_at 기준 유효 시간. None이면 무제한

DEFAULT_RETRY_POLICY = RetryPolicy(5, (5s, 30s, 2m, 10m), None)
```

전달 대상별 값은 [`event-delivery.md` 전달 대상별 정책](../product-specs/event-delivery.md#전달-대상별-정책-현재)이 정본이다.

### DEAD와 수동 재처리 (OUTBOX-REQ-006)

- `DEAD`가 되면 `logger.error`로 이벤트 ID·유형·전달 대상·오류를 남기고, `dead_alerted_at`이 비어 있으면 관리자 Slack 알림을 보내고 시각을 기록한다.
- 관리자 API (`/v1/admin/outbox`, 기존 관리자 인증):

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/v1/admin/outbox/deliveries?status=DEAD&consumer=&from=&to=&page=&size=` | 전달 목록 (기본 `DEAD`) |
| POST | `/v1/admin/outbox/deliveries/{deliveryId}/retry` | 단건 재처리 |
| POST | `/v1/admin/outbox/deliveries/retry?consumer=` | 전달 대상의 `DEAD` 일괄 재처리 (`consumer` 필수) |

- 재처리는 조건부 전이 한 문장으로 한다: `UPDATE event_deliveries SET status='PENDING', attempts=0, next_attempt_at=NULL, dead_alerted_at=NULL, manual_retry_count=manual_retry_count+1, last_manual_retry_by=:admin WHERE id=:id AND status='DEAD'`. 바뀐 행이 0이면 거부(`409`)한다. 동시에 두 요청이 와도 하나만 바뀐다.
- 재처리된 전달은 일반 전달 처리로 다시 돈다. 유효 시간도 그대로 적용되어 지난 전달은 `SKIPPED`로 끝난다.

### 정리 (OUTBOX-REQ-007)

- 매일 1회(새벽, APScheduler): 발행됐고(`published_at` 있음), 모든 전달이 `SUCCEEDED`·`SKIPPED`이고, 가장 늦은 `finished_at`이 7일 넘게 지난 이벤트를 전달 기록과 함께 삭제한다. 한 번에 1,000건씩 나눠 지운다.
- `DEAD`·`FAILED`·`PENDING`·`PROCESSING`이 하나라도 있거나 미발행이면 지우지 않는다.

## 이벤트 봉투 (OUTBOX-REQ-008)

```jsonc
{
  "eventId": "8f0c…",              // UUID, 중복 방지 키
  "eventType": "chat.message.created",
  "aggregateType": "chat_room",    // Kafka 토픽 선택 기준 (예: kkobungdan.chat)
  "aggregateId": "42",             // 순서 키 = Kafka 파티션 키
  "schemaVersion": 1,
  "occurredAt": "2026-11-17T05:00:00.000000Z",
  "payload": { … }
}
```

## Kafka 도입 시 (지금은 구현하지 않음)

| 바뀌는 곳 | 지금 | Kafka 도입 후 |
|-----------|------|---------------|
| `EventPublisher` | `InProcessEventPublisher`: 전달 행 생성 | `KafkaEventPublisher`: 토픽 = `aggregate_type`, 키 = `aggregate_id` |
| 전달 처리 입구 | 주기 작업이 `event_deliveries`를 집음 | Kafka consumer가 메시지를 받아 `event_deliveries` 행 확보 후 같은 처리 |
| consumer group | – | 전달 대상 이름 = group. 실시간처럼 인스턴스마다 받아야 하는 대상은 인스턴스별 group |
| 바뀌지 않음 | `outbox_events`, `record_event`, 봉투, `event_deliveries`(중복 방지·재시도·DEAD·재처리), 정책, 정리, 관리자 API | |

- Kafka 서버나 집 네트워크가 멈추면 발행이 실패하고 이벤트는 `outbox_events`에 남는다. 발행 재시도(최대 10분 간격)와 지연 알림(5분)이 그대로 동작해 이벤트를 잃지 않는다.
- Kafka의 DLQ 대신 `DEAD` + 수동 재처리를 쓴다. 필요하면 DLQ 토픽을 추가해도 `event_deliveries` 기록은 유지한다.

## 대안과 결정

| 대안 | 장점 | 단점 | 결정 |
|------|------|------|------|
| 커밋 후 메모리에서 바로 전달 | 테이블이 필요 없다 | 서버가 멈추면 이벤트를 잃는다 | 채택하지 않음 |
| 전달 대상별로 outbox 행을 따로 기록 | 재시도 단위가 단순하다 | 이벤트가 여러 행이 되고 Kafka 모델과 다르다 | 채택하지 않음. 이벤트 1행 + `event_deliveries` |
| 발행 실패도 횟수 제한 후 포기 | 무한 재시도가 없다 | 결제·정산 이벤트를 잃을 수 있다 | 채택하지 않음. 발행은 포기하지 않고 지연 알림으로 사람이 본다 |
| DEAD를 자동 삭제 | 테이블이 작게 유지된다 | 원인 확인·재처리 근거가 사라진다 | 채택하지 않음 |
| 처리 중 표시 없이 FAILED/PENDING만 | 상태가 적다 | 두 작업이 같은 전달을 동시에 처리할 수 있다 | 채택하지 않음. `PROCESSING` + 5분 임대 |
| 기존 `notifications` outbox 재사용 | 이미 있다 | 사용자 알림 목록과 섞인다 | 채택하지 않음. 기존 알림 이전은 결제·정산 때 검토 |

## 리스크

- 10초 처리 작업이 DB를 계속 조회한다(발행 대상·전달 대상·가장 오래된 미발행 이벤트). 인덱스로 가볍게 유지하고, 실제 부하를 보고 간격을 조정한다.
- 재시도 시각(예: 5초 뒤)이 되어도 다음 처리 작업(최대 10초 뒤)까지 기다린다. 실제 재시도 간격은 정책 값보다 최대 10초 길어질 수 있다.
- 발행 지연 알림 상태가 메모리에 있어 재시작 직후 같은 지연을 한 번 더 알릴 수 있다.
- 결과 기록 전 중단 시 한 번 더 처리될 수 있다(at-least-once). 전달 대상의 멱등성이 필수다.
