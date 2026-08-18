# 미입금 자동 취소 알림

## 목표

24시간 내 미입금으로 Proposal이 자동 취소될 때, 요청자에게 취소 알림을 발송한다.

## 배경

24시간 미입금 자동 취소 자체는 이미 동작한다.

- `ProposalService.cancel_expired_payment_proposals` — `HOLDING` 상태이며 `created_at`이 24시간 이전인 Proposal을 `CANCELLED`로 전환
- `app/tasks/payment_checker.py` — 위 함수를 감싸는 태스크
- `app/main.py` — APScheduler로 1시간마다 실행

문제는 **취소 사실을 사용자가 알 수 없다는 점**이다. 현재 구현은 `Query.update()` 일괄 UPDATE라 개별 Proposal을 순회하지 않고, 도메인 이벤트도 발행하지 않는다. 그래서 알림이 생성되지 않는다.

알림 인프라(`NotificationType.PROPOSAL_CANCELLED`, EventBus, `notification_listener`, outbox worker)는 이미 존재하므로 이벤트 발행과 리스너만 추가하면 된다.

## 범위

- `PaymentExpiredProposalCancelledEvent` 도메인 이벤트 추가
- `cancel_expired_payment_proposals`를 일괄 UPDATE에서 행 단위 처리로 변경하고, 취소 건마다 이벤트를 발행한다.
- `notification_listener`에 핸들러를 추가해 요청자에게 `PROPOSAL_CANCELLED` 알림을 생성한다.
- 스케줄러 태스크에서 생성된 PENDING 알림을 즉시 flush한다 (HTTP 요청 컨텍스트가 없어 `BackgroundTasks`를 쓸 수 없음).
- `notification-policy.md`에 24시간 미입금 취소 알림을 구현 완료로 기록한다.

## 비범위

- 만료 전 사전 예고(리마인드) 알림
- 30분 입금 독촉 알림 — 별개 이벤트로 2차 구현 대상에 유지한다.
- 취소 기준 시간 변경 (24시간 유지)
- 스케줄러 주기 변경 (1시간 유지)

## 정책 값

| 항목 | 값 |
|---|---|
| 취소 대상 | `status == HOLDING` 이고 `created_at <= now - 24h` |
| 알림 수신자 | Proposal 요청자(`orderer_id`) 1인 |
| 알림 타입 | `PROPOSAL_CANCELLED` |
| 알림 문구 | 제목 `의뢰가 취소되었습니다`, 본문에 미입금 사유 포함 |
| 발송 시점 | 스케줄러 실행 시점 (최대 1시간 지연 가능) |

`HOLDING`은 입금 전 단계라 아직 매칭된 러너가 없다. 따라서 수신자는 요청자 1인이다.

## 작업 분해

1. `app/events/proposal_events.py`에 `PaymentExpiredProposalCancelledEvent`를 정의한다.
2. `ProposalService.cancel_expired_payment_proposals`를 대상 조회 → 개별 상태 변경 → 이벤트 발행 순으로 변경한다.
3. `app/listeners/notification_listener.py`에 핸들러와 `EventBus.register`를 추가한다.
4. `app/tasks/payment_checker.py`에서 취소 후 PENDING 알림을 flush한다.
5. 테스트를 추가한다 (취소 시 알림 생성, 알림 비활성 사용자는 SKIPPED, 취소 대상 없으면 알림 없음).
6. `docs/product-specs/notification-policy.md`, `docs/domains/admin-payment-settlement/` 문서를 갱신한다.

## 검증 전략

- `pytest -q` 전체 통과
- 24시간 경과 `HOLDING` Proposal이 `CANCELLED`가 되고 요청자에게 `PROPOSAL_CANCELLED` 알림이 생성되는지 확인
- `alarm_enabled=false` 사용자는 알림이 `SKIPPED` 상태로 생성되는지 확인
- 24시간 미경과 Proposal은 취소·알림 모두 발생하지 않는지 확인

## 실제 반영 내용

| 파일 | 변경 |
| --- | --- |
| `app/events/proposal_events.py` | `PaymentExpiredProposalCancelledEvent` 신규 정의 |
| `app/services/proposal/proposal_service.py` | `cancel_expired_payment_proposals`를 일괄 UPDATE에서 행 단위 처리로 변경하고 취소 건마다 이벤트 발행 |
| `app/listeners/notification_listener.py` | `on_payment_expired_proposal_cancelled` 핸들러와 `EventBus.register` 추가 |
| `app/tasks/payment_checker.py` | 취소 후 PENDING 알림을 outbox worker로 직접 flush |
| `tests/conftest.py` | 리스너 등록을 session autouse fixture로 추가 |
| `tests/test_admin_integration.py` | 알림 생성/SKIPPED/미발생 테스트 3건 추가 |
| `docs/product-specs/notification-policy.md` | 결제 관련 알림 항목 추가, 30분 독촉을 별개 이벤트로 명시 |
| `docs/domains/admin-payment-settlement/` | README 책임과 test-scenarios 보장 범위 갱신 |

스키마 변경 없음. Alembic 마이그레이션 불필요.

## 검증 근거

- 실행일: 2026-08-16
- 환경: Python 3.12.14, MySQL 8.0 (`docker-compose.test.yml`, 포트 3307)
- 명령: `pytest -q`
- 결과: **165 passed** (기존 162 + 신규 3)
- 확인한 동작: 24시간 경과 `HOLDING` 취소 시 요청자에게 `PROPOSAL_CANCELLED` 알림 생성, `alarm_enabled=false`는 `SKIPPED`, 24시간 미경과 건은 취소·알림 모두 없음
- 단독 실행 검증: `pytest tests/test_admin_integration.py -k expired` 4 passed

## 작업 중 발견하여 함께 고친 것

이벤트 리스너 등록이 앱 시작 시점에만 이뤄져, `client` fixture를 쓰지 않고 서비스를 직접 호출하는 테스트는 리스너 없이 실행되어 조용히 실패했다. 기존 테스트는 모두 `client`를 거쳐 우연히 통과하고 있었다. `tests/conftest.py`에 session autouse fixture로 `register_all()`을 올려 실행 순서와 무관하게 동작하도록 했다.

## 남은 리스크와 후속 작업

- **알림 지연**: 스케줄러가 1시간 주기이므로 취소 시점과 알림 발송 사이에 최대 1시간 지연이 있다. 24시간 기준 정책에서는 허용 가능한 오차로 판단했다. 더 정확한 시점이 필요하면 주기를 줄인다.
- **30분 입금 독촉 알림 미구현**: `notification-policy.md`의 2차 구현 대상으로 유지된다. 이번 취소 알림과는 별개 이벤트다.
- **사전 예고 알림 없음**: 만료 전 리마인드는 이번 범위에서 제외했다. 입금 전환율 개선이 필요하면 별도 계획으로 다룬다.

## 상태

- [x] 구현
- [x] 테스트 통과 — 전체 165 passed (2026-08-16, 로컬 MySQL 8)
- [x] 문서 반영
- [x] 완료 — `completed/`로 이동
