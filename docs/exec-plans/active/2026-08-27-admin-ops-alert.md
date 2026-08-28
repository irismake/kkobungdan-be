# 관리자 운영 알림: 분쟁 접수·미션 완료를 Slack으로 통보

작성일: 2026-08-27 · 상태: 구현·로컬 검증 완료, Webhook 발급과 배포 검증 대기

## 배경

관리자가 직접 처리해야만 진행되는 지점이 두 곳 있는데, 지금은 관리자가 관리자 웹을 열어
목록을 새로고침하기 전까지 그 사실을 알 수 없다.

1. **분쟁 접수** — 행님 또는 꼬붕이 분쟁을 접수하면 미션이 `DISPUTED`가 된다. 이 미션은
   관리자가 완료/실패를 판정하기 전까지 어느 방향으로도 움직이지 않는다. 판정 전까지
   행님의 돈은 묶여 있고 꼬붕은 수행비를 못 받는다.
2. **미션 완료** — 양측이 만남을 확인하면 미션이 `COMPLETED`가 된다. `COMPLETED`는
   `docs/product-specs/mission.md`대로 **지급 대기 상태를 겸한다**. 관리자가 꼬붕 계좌로
   실제 이체를 하고 지급을 기록해야 `PAID`가 된다. 서버는 이체를 실행하지 않으므로
   관리자가 모르면 입금은 영원히 일어나지 않는다.

두 경우 모두 사용자 쪽 FCM 알림은 이미 나가지만(`DISPUTE_RAISED`, `EXECUTION_COMPLETED`)
**관리자에게 가는 경로가 없다.** 관리자 계정은 앱 사용자가 아니라 FCM 토큰도 없다.

## 결정 내용

### 채널: Slack Incoming Webhook

| 후보 | 발송 비용 | 문제 |
|---|---|---|
| **Slack Incoming Webhook** | **0원** (무료 플랜 포함, 건수 제한 없음) | 없음. 운영팀이 이미 쓰는 채널 |
| Discord Webhook | 0원 | 운영 채널이 Slack이라 채널을 하나 더 봐야 함 |
| Telegram Bot | 0원 | 봇 생성·chat_id 확보가 번거롭고 여러 명이 보려면 그룹 설정이 추가로 필요 |
| SMS (AWS SNS) | 건당 과금 | 이미 붙어 있지만 유일하게 돈이 든다. 알림당 원가가 발생 |
| 이메일 (AWS SES) | 1000건당 약 $0.10 | 도메인·발신 주소 검증과 샌드박스 해제가 선행돼야 하고 실시간성이 가장 낮다 |

Slack Incoming Webhook을 쓴다. 발송 비용 0원이고, 서버가 할 일은 webhook URL로 JSON을
POST하는 것뿐이라 SDK도 새 의존성도 필요 없다 — `httpx`는 이미 의존성에 있다.

Webhook URL은 **그 자체가 인증 수단**(URL을 아는 누구나 그 채널에 글을 쓸 수 있다)이므로
저장소에 커밋하지 않고 `ADMIN_ALERT_SLACK_WEBHOOK_URL` 환경변수와 GitHub Secret으로만 넣는다.

### 트리거: 미션 상태 전이 두 건만

요청 그대로 두 건만 보낸다. 다른 이벤트(지원 발생, 입금 확인, 신고 접수, 환불 대기)는
이번 범위가 아니다.

| 미션 전이 | 알림 내용 | 관리자가 할 일 |
|---|---|---|
| `STARTED` → `DISPUTED` | 분쟁이 접수됐다 | 관리자 웹에서 완료/실패 판정 |
| `STARTED`/`DISPUTED` → `COMPLETED` | 미션이 완료됐다 | 꼬붕에게 수행비 이체 후 지급 기록 |

`COMPLETED`는 **관리자가 분쟁을 완료로 판정해서 도달한 경우도 포함한다.** 판정한 사람과
수행비를 입금하는 사람이 같다는 보장이 없고, 판정 시점이 곧 지급 대기의 시작이기 때문이다.

`FAILED`(환불 대기)와 `PAID`(종료)는 이번에 알리지 않는다. `FAILED`는 관리자 본인의 판정
또는 관리자 요청 취소의 결과라 이미 관리자가 아는 상태다.

### 전이 감지 위치

미션 상태 전이는 세 곳에서 일어난다.

| 위치 | 전이 | 발생 경로 |
|---|---|---|
| `MissionService.sync_from_offer_and_proposal` | → `DISPUTED`, → `COMPLETED` | 앱: 분쟁 접수, 양측 만남 확인 |
| `MissionService.resolve_dispute` | → `COMPLETED` | 관리자 웹: `POST /v1/admin/missions/{id}/resolve` |
| `AdminCommandService.resolve_dispute` | → `COMPLETED` | 관리자 웹: `POST /v1/admin/disputes/{id}/resolve` |

`Mission.mark_disputed()`/`mark_completed()`는 허용되지 않는 상태에서 조용히 아무것도 하지
않는 no-op이다. 따라서 "메서드를 호출했으니 전이했다"고 볼 수 없고, **호출 전 상태를 들고
있다가 호출 후와 비교해서** 실제로 바뀐 경우에만 이벤트를 발행한다. 이렇게 하지 않으면
이미 `DISPUTED`인 미션에 대해 같은 알림이 반복해서 나간다.

모델(`Mission`)에는 알림 코드를 넣지 않는다. 영속 모델이 Slack을 알 이유가 없다.

### 발송 아키텍처: 기존 Outbox 패턴 재사용

FCM 알림이 쓰는 구조를 그대로 따른다. 새 인프라를 만들지 않는다.

```
[비즈니스 트랜잭션]
  MissionService / AdminCommandService
    → 전이 전후 상태 비교 → EventBus.publish(MissionDisputedEvent | MissionCompletedEvent, db)
        → AdminAlertListener → AdminAlert 를 db.info 에 적재 (DB 쓰기 없음)
    → db.commit()

[커밋 이후 발송 - FastAPI BackgroundTask]
  라우터의 _queue_created_notifications() 에서 함께 flush
    → pop_admin_alerts(db) → SlackAdminAlertSender.send() → Slack Incoming Webhook
```

**HTTP 호출을 트랜잭션 안에서 하지 않는 것이 핵심이다.** 리스너는 메시지를 조립해
`db.info`에 쌓기만 하고, 실제 POST는 커밋이 끝난 뒤 BackgroundTask에서 한다. 리스너에서
바로 Slack을 부르면 (1) DB 트랜잭션이 외부 네트워크 지연만큼 길어지고 (2) 이후 롤백된
트랜잭션에 대해서도 알림이 나가버린다.

`db.info`를 쓰는 이유는 `notification_outbox.py`가 이미 같은 방식으로 "이번 요청에서 생긴
알림"을 라우터까지 전달하고 있기 때문이다. 새 저장 방식을 만들 이유가 없다.

### 알림을 DB에 적재하지 않는 이유

FCM 알림과 달리 관리자 알림은 `notifications` 테이블에 남기지 않고, 발송 실패 시 재시도도
하지 않는다(로그만 남긴다).

- 관리자 알림의 **정본은 이미 관리자 웹에 있다.** 처리할 분쟁은 `DisputeEvidence.status=PENDING`
  목록이고, 입금할 미션은 `MissionStatus.COMPLETED` 목록이다. Slack 메시지는 그 목록을 보라는
  재촉이지 처리 대기열 자체가 아니다
- 따라서 Slack 메시지를 한 건 놓쳐도 일이 사라지지 않는다. 관리자 웹 목록에 그대로 남는다
- 재시도 큐와 전용 테이블을 만드는 비용이 이 실패 모드에 비해 크다

대신 발송 실패는 `logger.error`로 남겨서 webhook이 죽은 것을 로그에서 확인할 수 있게 한다.
이 트레이드오프는 tech-debt-tracker에 기록한다.

### 메시지 내용

계좌번호는 Slack에 싣지 않는다. 정산 계좌는 개인정보이고, Slack 채널은 서버 로그보다 접근
범위가 넓으며 검색·보존된다. 관리자 웹에서 확인하도록 링크만 건다.

`ADMIN_WEB_BASE_URL`이 설정돼 있으면 해당 화면 링크를 붙이고, 없으면 링크 줄만 뺀다.

```
🚨 분쟁이 접수됐어요 — 판정이 필요합니다
미션 #12 · 요청 #7 «편의점 담배 심부름»
행님 김가희 / 꼬붕 홍길동 · 수행비 15,000원
관리자 웹에서 완료 또는 실패로 판정해주세요.
```

```
💰 미션이 완료됐어요 — 수행비 입금이 필요합니다
미션 #12 · 요청 #7 «편의점 담배 심부름»
꼬붕 홍길동 · 입금 금액 15,000원
꼬붕 정산 계좌로 입금한 뒤 관리자 웹에 지급을 기록해주세요.
```

### 미설정 시 동작: 조용히 끈다

`ADMIN_ALERT_SLACK_WEBHOOK_URL`이 없으면 기동 시 경고 로그 한 줄을 남기고 발송을 건너뛴다.
CORS와 달리 **기동을 실패시키지 않는다.** 알림은 운영 편의 기능이고, 없다고 해서 잘못된
상태로 서비스가 도는 것이 아니다. 로컬 개발과 테스트에서 webhook 없이 그대로 떠야 한다.

## 작업 항목

1. `app/core/config.py`: `admin_alert_slack_webhook_url`, `admin_web_base_url` 추가
2. `app/events/mission_events.py` (신규): `MissionDisputedEvent`, `MissionCompletedEvent`
3. `app/services/admin_alert_service.py` (신규): `AdminAlert` 데이터 클래스,
   `SlackAdminAlertSender`, `get_admin_alert_sender()`
4. `app/services/admin_alert_outbox.py` (신규): `track_admin_alert`, `pop_admin_alerts`,
   `queue_admin_alerts(background_tasks, db)`
5. `app/listeners/admin_alert_listener.py` (신규): 두 이벤트 → 메시지 조립 → outbox 적재
6. `app/services/mission/mission_service.py`: `sync_from_offer_and_proposal`,
   `resolve_dispute`에 전이 전후 비교와 이벤트 발행 추가
7. `app/services/admin/admin_command_service.py`: `resolve_dispute`에 동일 처리 추가
8. `app/api/v1/offer/offer_router.py`, `proposal_router.py`, `admin_router.py`:
   기존 `_queue_created_notifications`에서 관리자 알림도 함께 flush.
   `resolve_mission`, `resolve_admin_dispute`에 `background_tasks` 파라미터 추가
9. `app/main.py`: `admin_alert_listener.register_all()` 등록, webhook 미설정 시 경고
10. `tests/conftest.py`: 기록형 가짜 sender로 교체
11. `tests/test_admin_alert_integration.py` (신규)
12. 배포 설정: `docker-compose.ec2.yml`, 두 배포 워크플로에 환경변수 주입
13. 문서: `docs/product-specs/notification-policy.md`에 관리자 운영 알림 절 추가,
    `ARCHITECTURE.md`, `README.md`(환경변수), `docs/exec-plans/tech-debt-tracker.md`

## 검증 기준

- 꼬붕이 분쟁을 접수하면 Slack에 분쟁 알림이 1건 발송된다
- 행님이 분쟁을 접수해도 동일하게 1건 발송된다
- 이미 `DISPUTED`인 미션에서 중복 발송되지 않는다
- 양측이 만남을 확인해 미션이 `COMPLETED`가 되면 입금 요청 알림이 1건 발송된다
- 꼬붕만 확인한 중간 시점에는 아무 알림도 나가지 않는다
- 관리자가 분쟁을 완료로 판정하면 입금 요청 알림이 1건 발송된다
  (`/admin/missions/{id}/resolve`, `/admin/disputes/{id}/resolve` 두 경로 모두)
- 관리자가 분쟁을 실패로 판정하면 알림이 나가지 않는다
- 관리자가 지급을 기록해 `PAID`가 될 때 알림이 나가지 않는다
- webhook URL 미설정 상태에서 위 흐름이 모두 예외 없이 200을 반환한다
- Slack POST가 실패해도 API 응답은 200이고 `logger.error`만 남는다
- 기존 FCM 알림 흐름에 회귀가 없다 (`pytest`)

## 남는 문제

- **발송 실패 시 유실**: 재시도·영속화가 없다. 관리자 웹 목록이 정본이므로 일이 사라지지는
  않지만, webhook이 장시간 죽어 있으면 재촉이 통째로 없어진다. 재시도가 필요해지면 FCM과
  같은 outbox 테이블로 승격한다
- **채널 하나만 지원**: 분쟁과 지급을 다른 채널로 나누려면 webhook URL을 종류별로 받아야 한다
- **꼬붕 정산 계좌 미노출**: 개인정보라 의도적으로 제외했다. 관리자가 매번 관리자 웹을 열어야
  입금할 수 있다
- **`ADMIN_WEB_BASE_URL` 미확정**: 관리자 웹 도메인을 이 저장소에서 확인할 수 없다. 값 없이도
  동작하되 링크 줄만 빠진다
