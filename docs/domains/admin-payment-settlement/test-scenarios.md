# Admin/Payment/Settlement Test Scenarios

기준 테스트 파일: `tests/test_admin_integration.py`, `tests/test_admin_web_api_integration.py`,
`tests/test_mission_integration.py`, `tests/test_refund_lifecycle.py`

## 입금 확인과 자동 취소 (`test_admin_integration.py`)

- 결제 확인은 request body 없이 `HOLDING` Proposal을 공개 상태로 전환하고 오픈채팅방 링크를 저장한다.
- 결제 확인은 `HOLDING`이 아닌 Proposal과 형식이 잘못된 오픈채팅방 링크를 거부한다.
- 결제 확인은 요청자에게 알림을 생성한다.
- 입금 확인 대기 Proposal은 생성 후 24시간이 지나면 스케줄러에 의해 `CANCELLED`로 전환된다.
- 미입금 자동 취소 시 요청자에게 `PROPOSAL_CANCELLED` 알림이 생성되고, 알림 비활성 사용자는 `SKIPPED`로 저장된다.

## 관리자 웹 처리 (`test_admin_web_api_integration.py`)

- 요청 취소는 연결된 지원과 미션을 함께 종결하고, 이미 취소된 요청은 거부한다.
- 입금 확인된 매칭 전 요청을 취소하면 `ADMIN_CANCELLED` 환불이 생성된다.
- 분쟁 판정이 `COMPLETED`면 미션은 `COMPLETED`, 요청·지원은 `ALL_COMPLETED`가 된다.
- 분쟁 판정이 `FAILED`면 미션은 `FAILED`가 되고 환불이 생성된다.
- 분쟁 반려는 요청·지원·미션 상태를 바꾸지 않는다.
- 이미 검토된 분쟁의 재판정은 거부한다.
- 환불 목록은 대기 환불을 Proposal 상태와 함께 반환하고, 상세는 마스킹하지 않은 계좌를 노출한다.
- 환불 완료 기록은 Refund를 `COMPLETED`로, Proposal을 `REFUNDED`로 전이한다.
- 수행비 지급 목록은 `COMPLETED` 미션만 반환하고, 지급 기록은 미션을 `PAID`로 전이한다.
- 수행비 지급 반려는 미션 상태를 `COMPLETED`로 유지한다.
- 관리자 요약은 도메인별 미처리 건수를 집계한다.

## 미션 상태 파생 (`test_mission_integration.py`)

- 지원 수락은 미션을 `STARTED`로 생성하고, 앱 응답에는 미션을 노출하지 않는다.
- 양측 완료 확인은 미션을 `COMPLETED`로, 어느 쪽의 분쟁 접수든 미션을 `DISPUTED`로 전이한다.
- `DISPUTED`가 아닌 미션의 판정과 종료 상태 미션의 재판정은 거부한다.
- `COMPLETED`가 아닌 미션의 지급 기록과 중복 지급은 거부한다.
- 미션 목록은 상태로 필터링되며, 응답에 양측 확인 시각·참여자 이름·오픈채팅방 링크를 담는다.
- 레거시 Offer 분쟁 해결 엔드포인트는 제거되어 존재하지 않는다.

## 환불 수명주기 (`test_refund_lifecycle.py`)

- 제거된 `RESOLVED`, Mission `REFUNDED`, 환불 반려 상태는 계약에 남아 있지 않다.
- 완료 판정은 요청·지원을 `ALL_COMPLETED`로, 실패 판정은 요청을 `REFUND_PENDING`, 지원을 `CANCELLED`로 전이한다.
- 환불 완료는 요청을 `REFUNDED`로 전이하고, 이미 처리된 환불의 재처리는 거부한다.
- 매칭 전 취소는 `HOLDING`이면 `CANCELLED`, 입금 확인 후면 `REFUND_PENDING`으로 갈린다.
