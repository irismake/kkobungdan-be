# 누락 알림 3건 구현 (입금 확인 / 미션 시작 / 입금 독촉)

## 목표

기획 스펙에 있으나 미구현 상태인 알림 3건을 구현한다.

1. 입금 확인 → 게시물 등록 완료 (요청자)
2. 지원자 선택 & 미션 시작 (요청자)
3. 입금 미확인 독촉 30분 (요청자)

## 배경

[`../../product-specs/notification-policy.md`](../../product-specs/notification-policy.md) 대조 결과 스펙 12건이 미구현이다. 그중 채팅방·정산 의존 4건과 환불 정책이 선행돼야 하는 게시물 만료, 상태 추적이 필요한 만남 확인 리마인드 4건을 제외한 3건을 먼저 처리한다.

- 1번: 관리자가 입금을 확인해 `HOLDING → POSTED`로 바뀌어도 요청자가 알 수 없다.
- 2번: 지원자 수락 시 지원자·탈락자에게만 알림이 가고 요청자는 받지 못한다.
- 3번: 입금 안내 후 30분이 지나도 아무 안내가 없고, 24시간 뒤 취소 알림이 첫 연락이 된다.

## 범위

- `ProposalPaymentConfirmedEvent`, `PaymentReminderDueEvent` 도메인 이벤트 추가
- `OfferAcceptedEvent` 처리에 요청자 대상 `PROPOSAL_MATCHED` 알림 추가 (이벤트 필드 변경 없음)
- `NotificationType.PAYMENT_REMINDER` 추가 (컬럼이 `String(50)`이라 마이그레이션 불필요)
- 30분 독촉 발송 스케줄러 태스크와 잡 등록 (10분 주기)
- 관리자 `confirm-payment` 엔드포인트에서 생성된 알림을 flush

## 비범위

- 게시물 만료(48시간) — 환불 정책 선행 필요
- 만남 확인 리마인드 1·2차 — 상대 확인 시각 기준 추적 필요
- 채팅방/정산 관련 알림 — 선행 기능 없음
- 디바운스·묶음 발송 규칙

## 정책 값

| 항목 | 값 |
|---|---|
| 게시물 등록 완료 | `PAYMENT_COMPLETED`, 요청자, `confirm_payment` 즉시 |
| 미션 시작 | `PROPOSAL_MATCHED`, 요청자, 지원자 수락 즉시 |
| 입금 독촉 | `PAYMENT_REMINDER`, 요청자, 생성 후 30분 경과 `HOLDING` |
| 독촉 대상 범위 | `created_at`이 30분 전 ~ 24시간 전 사이 (24시간 초과는 취소 대상이므로 제외) |
| 독촉 중복 방지 | 같은 Proposal에 `PAYMENT_REMINDER` 알림이 이미 있으면 건너뜀 |
| 독촉 스케줄러 주기 | 10분 (30분 기준 대비 최대 10분 지연) |

## 작업 분해

1. `app/models/notification.py`에 `PAYMENT_REMINDER` 추가한다.
2. `app/events/proposal_events.py`에 이벤트 2종을 추가한다.
3. `ProposalService.confirm_payment`에서 이벤트를 발행한다.
4. `ProposalService.send_payment_reminders`를 추가한다 (대상 조회 → 중복 제외 → 이벤트 발행).
5. `notification_listener`에 핸들러 3개를 추가하고 등록한다.
6. `app/tasks/payment_checker.py`에 독촉 태스크를 추가하고 `main.py`에 10분 주기 잡을 등록한다.
7. 관리자 라우터 `confirm-payment`에 알림 flush를 추가한다.
8. 테스트를 추가한다.
9. `notification-policy.md` 구현 상태를 갱신한다.

## 검증 전략

- `pytest -q` 전체 통과
- 입금 확인 시 요청자에게 `PAYMENT_COMPLETED` 알림 생성
- 지원자 수락 시 요청자에게 `PROPOSAL_MATCHED`, 지원자에게 `OFFER_ACCEPTED`가 함께 생성
- 30분 경과 `HOLDING`에 독촉 1건 생성, 재실행 시 중복 생성 없음
- 30분 미경과 및 24시간 초과 건은 독촉 대상에서 제외

## 실제 반영 내용

| 파일 | 변경 |
| --- | --- |
| `app/models/notification.py` | `PAYMENT_REMINDER` 타입 추가 |
| `app/events/proposal_events.py` | `ProposalPaymentConfirmedEvent`, `PaymentReminderDueEvent` 추가 |
| `app/services/proposal/proposal_service.py` | `confirm_payment` 이벤트 발행, `send_payment_reminders` 추가, `PAYMENT_DEADLINE`·`PAYMENT_REMINDER_DELAY` 상수와 `_as_naive_utc` 헬퍼로 시간 처리 정리 |
| `app/listeners/notification_listener.py` | 핸들러 2개 추가, `on_offer_accepted`에 요청자 `PROPOSAL_MATCHED` 알림 추가 |
| `app/tasks/payment_checker.py` | `send_pending_payment_reminders` 태스크 추가 |
| `app/main.py` | 독촉 잡 10분 주기 등록 |
| `app/api/v1/admin/admin_router.py` | `confirm-payment`에 알림 flush 추가 |
| `tests/conftest.py` | admin 라우터 notification worker 스텁 추가 |
| `tests/test_admin_integration.py` | 입금 확인 알림, 독촉 대상/중복 방지, SKIPPED 테스트 3건 추가 |
| `tests/test_offer_integration.py` | 수락 시 요청자 알림 0건 검증을 `PROPOSAL_MATCHED` 1건 검증으로 변경 |
| `docs/product-specs/notification-policy.md` | 구현 상태 3건 갱신, 스케줄러 주기와 저장 필드 규칙 보강 |

`notification_type` 컬럼이 `String(50)`이라 타입 추가에 마이그레이션이 필요 없다.

## 검증 근거

- 실행일: 2026-08-16
- 환경: Python 3.12.14, MySQL 8.0 (`docker-compose.test.yml`, 포트 3307)
- 명령: `pytest -q`
- 결과: **168 passed** (기존 165 + 신규 3)
- 확인한 동작: 입금 확인 시 `PAYMENT_COMPLETED` 생성, 수락 시 요청자 `PROPOSAL_MATCHED` + 지원자 `OFFER_ACCEPTED` 동시 생성, 30분 경과 건에만 독촉 1건 생성 후 재실행 시 중복 없음, 30분 미경과·24시간 초과·입금 완료 건 제외, `alarm_enabled=false`는 `SKIPPED`

## 작업 중 발견하여 함께 고친 것

`tests/conftest.py`가 offer·proposal 라우터의 notification worker만 스텁으로 대체하고 있어, admin 라우터에 알림 flush를 추가하자 테스트가 실제 운영 DB로 접속을 시도했다. admin 라우터 스텁을 추가해 해결했다. 라우터에 알림 발송을 추가할 때마다 이 목록을 갱신해야 한다.

## 남은 리스크와 후속 작업

- **독촉 중복 방지 방식**: 별도 플래그 컬럼 없이 `PAYMENT_REMINDER` 알림 존재 여부로 판정한다. 알림 레코드를 삭제하면 재발송될 수 있다.
- **발송 지연**: 독촉은 10분 주기이므로 30분 기준 대비 최대 10분 늦게 발송된다.
- **랜딩 페이지 미지원**: 스펙의 랜딩 페이지를 전달할 payload 필드가 없다. 신규 알림 3건도 동일한 제약을 받는다.
- **미구현 잔여 9건**: 채팅방 4건, 만남 확인 리마인드 4건, 정산 완료 1건, 게시물 만료 1건. 게시물 만료는 환불 정책이 선행돼야 한다.

## 상태

- [x] 구현
- [x] 테스트 통과 — 전체 168 passed (2026-08-16, 로컬 MySQL 8)
- [x] 문서 반영
- [x] 완료 — `completed/`로 이동
