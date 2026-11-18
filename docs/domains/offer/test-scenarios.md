# Offer Test Scenarios

기준 테스트 파일: `tests/test_offer_integration.py`

## 보장 범위

- Offer 생성은 `proposalId`와 첫 인사(`greeting`, 필수)를 입력으로 받고 Proposal을 `OFFERED`로 전이한다. 같은 트랜잭션에서 채팅방과 첫 인사가 저장된다([`../chat/test-scenarios.md`](../chat/test-scenarios.md) CHAT-TS-001, 016, 017).
- 두 번째 Offer 생성은 Proposal을 `OFFERED`로 유지한다.
- 목록/내 목록 조회는 최신순 정렬, 페이징, 반복 `status` 필터를 지원한다.
- Proposal별 목록 조회는 상세 조회와 별도 DTO를 사용하며 오픈채팅방 링크를 반환하지 않는다.
- 상세 조회는 인증된 사용자에게 Offer 상태와 수락 이후 timestamp를 반환한다.
- 상세 조회는 수락 이후 상태에서 행님과 해당 꼬붕에게만 오픈채팅방 링크를 반환하고, 그 외에는 null을 반환한다.
- Offer 수락은 선택 Offer를 `ACCEPTED`, 같은 Proposal의 다른 대기 Offer를 `REJECTED`, Proposal을 `MATCHED`로 전이하고 수락 timestamp를 기록한다.
- 이미 활성 수락 Offer가 있으면 추가 수락을 막는다.
- 취소는 꼬붕 본인과 `WAITING` 상태 규칙을 따른다.
- 꼬붕 완료는 Offer를 `RUNNER_COMPLETED` 또는 `ALL_COMPLETED`로 전이하고 Proposal 상태와 동기화한다.
- 꼬붕 분쟁은 active `RUNNER` 설문 질문 ID와 사유를 DisputeEvidence에 기록하고, `ACCEPTED` 또는 `RUNNER_COMPLETED`에서 Offer와 Proposal을 `DISPUTED`로 전이하고 timestamp를 기록한다. 사유 선택은 필수이고, `requiresDetail`이 `true`인 사유(기타)를 고를 때만 상세 사유가 필수다.
- 꼬붕 분쟁은 누락, 비활성, 대상 불일치 설문 질문 ID를 거절한다.
- 꼬붕 분쟁은 `ALL_COMPLETED`에서 거절되며 상태와 timestamp를 유지한다.
- 꼬붕 분쟁은 알림이 켜진 행님에게 분쟁 알림을 생성한다.
- validation, 권한, 상태 오류는 정본 에러 계약을 따른다.

## 시나리오 목록

시나리오 ID는 테스트의 `@pytest.mark.scenario("OFFER-TS-NNN")`와 1:1로 연결된다 ([`tdd-workflow.md`](../../design-docs/tdd-workflow.md)).

| ID | 보장 내용 | 테스트 |
|----|-----------|--------|
| OFFER-TS-001 | 지원 생성은 `proposalId`와 첫 인사(`greeting`)를 받고 요청을 `OFFERED`로 바꾼다 | `test_offer_integration.py::test_create_offer_with_greeting_marks_proposal_offered` |
| OFFER-TS-002 | 꼬붕의 정산 계좌가 없으면 지원할 수 없다 | `test_offer_integration.py::test_create_offer_requires_runner_settlement_account` |
| OFFER-TS-003 | 지원 생성 시 알림이 켜진 행님·꼬붕에게 알림이 생긴다 | `test_offer_integration.py::test_create_offer_creates_notifications_for_alarm_enabled_users` |
| OFFER-TS-004 | 알림이 꺼진 사용자의 지원 알림은 `SKIPPED`로 저장된다 | `test_offer_integration.py::test_create_offer_stores_skipped_notifications_when_alarm_disabled` |
| OFFER-TS-005 | 지원 생성은 이번 사건에서 만든 알림만 발송 대기열에 넣는다 | `test_offer_integration.py::test_create_offer_queues_only_notifications_created_by_current_event` |
| OFFER-TS-006 | 두 번째 지원도 요청을 `OFFERED`로 유지한다 | `test_offer_integration.py::test_create_second_offer_keeps_proposal_offered` |
| OFFER-TS-007 | 지원 목록은 최신순이고 다중 상태 필터를 지원한다 | `test_offer_integration.py::test_get_offers_returns_latest_first_and_supports_multi_status_filter` |
| OFFER-TS-008 | 지원 상세는 로그인한 사용자 누구나 조회할 수 있다 | `test_offer_integration.py::test_get_offer_detail_allows_any_logged_in_user` |
| OFFER-TS-009 | 수락 이후 지원 상세는 상태 전이 시각을 반환한다 | `test_offer_integration.py::test_get_offer_detail_returns_state_timestamps_when_accepted` |
| OFFER-TS-010 | 지원 상세의 오픈채팅방 링크는 매칭된 행님·꼬붕에게만 내려간다 | `test_offer_integration.py::test_get_offer_detail_returns_open_chat_url_only_to_matched_participants` |
| OFFER-TS-011 | 수락 전 지원 상세는 오픈채팅방 링크를 null로 내려준다 | `test_offer_integration.py::test_get_offer_detail_masks_open_chat_url_before_accepted_status` |
| OFFER-TS-012 | 내 지원 목록은 페이징과 다중 상태 필터를 지원한다 | `test_offer_integration.py::test_get_own_offers_supports_paging_and_multi_status_filter` |
| OFFER-TS-013 | 내 지원 목록은 배지 순으로 묶고 같은 배지 안에서는 최신순이다 | `test_offer_integration.py::test_get_own_offers_orders_by_badge_then_latest` |
| OFFER-TS-014 | 지원 수락은 선택 지원 `ACCEPTED`, 나머지 `REJECTED`, 요청 `MATCHED`로 바꾸고 시각을 기록한다 | `test_offer_integration.py::test_accept_offer_updates_states_and_timestamps` |
| OFFER-TS-015 | 지원 수락 시 선택·미선정 꼬붕에게 각각 알림이 생긴다 | `test_offer_integration.py::test_accept_offer_creates_selected_and_rejected_runner_notifications` |
| OFFER-TS-016 | 알림이 꺼진 꼬붕의 수락 알림은 `SKIPPED`로 저장된다 | `test_offer_integration.py::test_accept_offer_stores_skipped_runner_notifications_when_alarm_disabled` |
| OFFER-TS-017 | 지원 수락의 권한·상태·입력 오류는 정본 에러로 거부된다 | `test_offer_integration.py::test_accept_offer_domain_and_validation_errors` |
| OFFER-TS-018 | 이미 수락된 지원이 있으면 추가 수락을 막는다 | `test_offer_integration.py::test_existing_active_offer_blocks_accept` |
| OFFER-TS-019 | 지원 취소는 꼬붕 본인과 `WAITING` 상태 규칙을 따른다 | `test_offer_integration.py::test_cancel_offer_author_and_status_rules` |
| OFFER-TS-020 | 꼬붕의 임무 완료는 지원을 `RUNNER_COMPLETED`로 바꾸고 요청은 끝내지 않는다 | `test_offer_integration.py::test_complete_delivery_marks_offer_completed_without_finishing_proposal` |
| OFFER-TS-021 | 꼬붕이 임무를 완료하면 행님에게 임무 완료 알림이 생긴다 | `test_offer_integration.py::test_complete_delivery_creates_meeting_confirmed_notification_for_orderer` |
| OFFER-TS-022 | 행님 확인 뒤 꼬붕이 완료하면 요청과 지원이 모두 `ALL_COMPLETED`가 된다 | `test_offer_integration.py::test_complete_delivery_after_orderer_completion_marks_both_all_completed` |
| OFFER-TS-023 | 양측 임무 완료 시 행님·꼬붕에게 임무 수행 완료 알림이 생긴다 | `test_offer_integration.py::test_complete_delivery_after_orderer_completion_creates_execution_completed_notifications` |
| OFFER-TS-024 | 꼬붕 레벨은 완료한 지원 수만큼 오른다 | `test_offer_integration.py::test_runner_level_counts_each_completed_offer` |
| OFFER-TS-025 | 꼬붕 분쟁 접수는 지원과 요청을 `DISPUTED`로 바꾸고 시각을 기록한다 | `test_offer_integration.py::test_raise_offer_dispute_updates_both_statuses_and_timestamps` |
| OFFER-TS-026 | 꼬붕 분쟁 접수는 누락·비활성·대상 불일치 설문 질문을 거부한다 | `test_offer_integration.py::test_raise_offer_dispute_rejects_invalid_survey_question` |
| OFFER-TS-027 | 꼬붕 분쟁 사유는 필수이고 기타 사유일 때만 상세 사유가 필수다 | `test_offer_integration.py::test_raise_offer_dispute_requires_detail_only_for_etc_reason` |
| OFFER-TS-028 | `ALL_COMPLETED` 지원은 꼬붕 분쟁 접수를 거부하고 상태를 유지한다 | `test_offer_integration.py::test_raise_offer_dispute_rejects_all_completed` |
| OFFER-TS-029 | 꼬붕 임무 완료는 본인이 아니거나 상태가 맞지 않으면 거부된다 | `test_offer_integration.py::test_complete_delivery_forbidden_and_wrong_status_errors` |
| OFFER-TS-030 | 지원 API의 입력·도메인 오류는 정본 에러 계약을 따른다 | `test_offer_integration.py::test_offer_validation_and_domain_errors` |
