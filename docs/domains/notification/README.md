# Notification/SMS Domain

Notification/SMS는 사용자 알림 조회/읽음 처리와 SMS provider 연동을 담당한다.

## 책임

- 알림 목록, 통계, 상세 조회, 읽음 처리를 제공한다.
- 관리자가 처리해야 진행되는 미션 전이(분쟁 접수, 미션 완료)를 관리자 채널로 통보한다.
- 알림 발송 성공과 실패 케이스를 API 계약에 맞춘다.
- AWS SNS 발송 형식, 속성, provider error 전파를 서비스 단위에서 검증한다.

## 계층 기준

- Notification API 라우터는 인증 사용자 주입, 요청 파라미터, 응답 래핑만 담당한다.
- 알림 목록 조회, 통계 계산, 상세 조회 권한 필터, 읽음 상태 변경은 `NotificationService`에서 처리한다.
- 알림 발송 저장/전송 흐름은 기존 `NotificationDispatcher`, `FCMService`, `NotificationWorker` 책임을 유지한다.
- 관리자 운영 알림(Slack)은 사용자 알림과 경로를 공유하지 않는다. `admin_alert_listener`가 미션 전이
  이벤트를 `AdminAlert`로 바꿔 `admin_alert_outbox`에 쌓고, 커밋 이후 BackgroundTask가
  `SlackAdminAlertSender`로 발송한다. `notifications` 테이블에 남기지 않고 재시도도 하지 않는다.

## 정본 링크

- 제품 정책: [`../../product-specs/notification-policy.md`](../../product-specs/notification-policy.md)
- FCM payload 계약: [`../../api-spec/notification-fcm-payload.md`](../../api-spec/notification-fcm-payload.md)
- API 계약: [`../../api-spec/README.md`](../../api-spec/README.md)의 Notification API
- 테스트 보장: [`test-scenarios.md`](./test-scenarios.md)
