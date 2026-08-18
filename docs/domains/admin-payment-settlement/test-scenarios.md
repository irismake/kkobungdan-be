# Admin/Payment/Settlement Test Scenarios

기준 테스트 파일: `tests/test_admin_integration.py`

## 보장 범위

- 결제 확인은 request body 없이 `HOLDING` Proposal을 공개 상태로 전환한다.
- 결제 확인은 `HOLDING`이 아닌 Proposal을 거부한다.
- 입금 확인 대기 Proposal은 생성 후 24시간이 지나면 스케줄러에 의해 `CANCELLED`로 전환된다.
- 미입금 자동 취소 시 요청자에게 `PROPOSAL_CANCELLED` 알림이 생성되고, 알림 비활성 사용자는 `SKIPPED`로 저장된다.
- 정산 확정은 완료 상태의 Offer만 처리한다.
- 분쟁 해결은 분쟁 상태의 Offer를 `RESOLVED`로 전이한다.
