# Proposal Test Scenarios

기준 테스트 파일: `tests/test_proposal_integration.py`, `tests/test_proposal_report_integration.py`

## 보장 범위

- 공개 Proposal 목록은 인증을 요구하고 `POSTED/OFFERED` 상태만 반환하며 반복 `status` 쿼리로 이를 필터링한다.
- 공개 Proposal 목록은 `deadline`이 빠른 순서로 반환하고, 동률이면 최신 생성 항목을 우선한다.
- 상세 조회는 Proposal 상태와 무관하게 존재하는 요청을 반환하며, 매칭 이후 상태 timestamp를 노출한다.
- 상세 조회는 매칭 이후 상태에서 행님과 수락된 꼬붕에게만 오픈채팅방 링크를 반환하고, 그 외에는 null을 반환한다.
- 내 Proposal 목록은 현재 사용자 요청만 반환하고 연결된 Offer 요약과 다중 상태 필터를 포함하며, `deadline`이 빠른 순서로 반환한다.
- 생성은 계약 필드와 validation을 검증하고 초기 상태를 `HOLDING`으로 저장한다.
- 수정과 취소는 작성자 권한, 상태 규칙, 대기 Offer 정리 규칙을 검증한다.
- 취소는 `HOLDING`이면 `CANCELLED`, 입금 확인된 `POSTED`/`OFFERED`면 `REFUND_PENDING`으로 전이하고, 대기 Offer를 `REJECTED`로 정리한다.
- 행님 수령 확인은 Proposal을 `ORDER_COMPLETED` 또는 `ALL_COMPLETED`로 전이하고 Offer 상태와 동기화한다.
- 행님 분쟁 접수는 active `ORDER` 설문 질문 ID와 사유를 DisputeEvidence에 기록하고, `MATCHED` 또는 `ORDER_COMPLETED`에서 Proposal과 수락된 Offer를 `DISPUTED`로 전이하고 timestamp를 기록한다. 사유 선택은 필수이고, `requiresDetail`이 `true`인 사유(기타)를 고를 때만 상세 사유가 필수다.
- 행님 분쟁 접수는 누락, 비활성, 대상 불일치 설문 질문 ID를 거절한다.
- 행님 분쟁 접수는 `ALL_COMPLETED`에서 거절되며 상태와 timestamp를 유지한다.
- 행님 분쟁 접수는 알림이 켜진 꼬붕에게 분쟁 알림을 생성한다.
- 게시글 신고는 다른 사용자의 공개 모집 상태 Proposal에 한해 생성하며, 사용자당 게시글별 한 건만 허용한다. 사유 항목은 필수이고, `requiresDetail`이 `true`인 사유(기타)를 고를 때만 상세 사유가 필수다.
- 관리자 신고 승인은 Proposal을 `REPORTED`로 전환하고 대기 Offer를 거절하며 공개 목록에서 제외한다. 반려는 Proposal 상태를 바꾸지 않고 신고 이력을 유지한다.
- ORM 모델 계약은 문서화된 필드와 enum 정책이 구현에 남아 있는지 확인한다.

## 시나리오 목록

시나리오 ID는 테스트의 `@pytest.mark.scenario("PROPOSAL-TS-NNN")`와 1:1로 연결된다 ([`tdd-workflow.md`](../../design-docs/tdd-workflow.md)).

| ID | 보장 내용 | 테스트 |
|----|-----------|--------|
| PROPOSAL-TS-001 | 공개 요청 목록은 인증이 필요하고 반복 `status` 필터를 지원한다 | `test_proposal_integration.py::test_list_public_requires_auth_and_supports_multi_status_filter` |
| PROPOSAL-TS-002 | 공개 요청 목록은 마감 기한과 관계없이 최신 생성 순으로 정렬된다 | `test_proposal_integration.py::test_list_public_orders_by_latest_creation_time` |
| PROPOSAL-TS-003 | 요청 상세는 상태와 관계없이 존재하는 요청을 반환한다 | `test_proposal_integration.py::test_detail_returns_proposal_regardless_of_status` |
| PROPOSAL-TS-004 | 매칭 이후 요청 상세는 상태 전이 시각을 반환한다 | `test_proposal_integration.py::test_detail_returns_state_timestamps_when_matched` |
| PROPOSAL-TS-005 | 요청 상세의 오픈채팅방 링크는 매칭된 행님·꼬붕에게만 내려간다 | `test_proposal_integration.py::test_detail_returns_open_chat_url_only_to_matched_participants` |
| PROPOSAL-TS-006 | 매칭 전 요청 상세는 오픈채팅방 링크를 null로 내려준다 | `test_proposal_integration.py::test_detail_masks_open_chat_url_before_matched_status` |
| PROPOSAL-TS-007 | 내 요청 목록은 본인 요청만 지원 요약과 함께 반환하고 다중 상태 필터를 지원한다 | `test_proposal_integration.py::test_list_own_returns_only_current_user_with_offers_and_multi_status_filter` |
| PROPOSAL-TS-008 | 내 요청 목록은 배지 순으로 묶고 같은 배지 안에서는 최신순이다 | `test_proposal_integration.py::test_list_own_orders_by_badge_then_latest` |
| PROPOSAL-TS-009 | 요청 생성은 계약 필드를 검증하고 `HOLDING`으로 저장한다 | `test_proposal_integration.py::test_create_proposal_validates_contract_and_stores_holding` |
| PROPOSAL-TS-010 | 정산 계좌가 없으면 요청을 생성할 수 없다 (`409 SETTLEMENT_ACCOUNT_REQUIRED`) | `test_proposal_integration.py::test_create_proposal_requires_settlement_account` |
| PROPOSAL-TS-011 | 요청 생성의 입력값 오류는 `400 VALIDATION_ERROR`로 거부된다 | `test_proposal_integration.py::test_create_proposal_validation_errors` |
| PROPOSAL-TS-012 | 요청 수정은 작성자 권한과 상태 규칙을 따른다 | `test_proposal_integration.py::test_update_proposal_author_and_status_rules` |
| PROPOSAL-TS-013 | 요청 취소는 작성자·상태 규칙을 따르고 대기 지원을 `REJECTED`로 정리한다 | `test_proposal_integration.py::test_cancel_proposal_author_status_rules_and_rejects_waiting_offers` |
| PROPOSAL-TS-014 | 행님의 임무 완료 확인은 요청을 `ORDER_COMPLETED`로 바꾸고 지원은 끝내지 않는다 | `test_proposal_integration.py::test_confirm_received_marks_proposal_completed_without_finishing_offer` |
| PROPOSAL-TS-015 | 행님이 임무 완료를 확인하면 꼬붕에게 임무 완료 확인 알림이 생긴다 | `test_proposal_integration.py::test_confirm_received_creates_meeting_confirmed_notification_for_runner` |
| PROPOSAL-TS-016 | 꼬붕 완료 뒤 행님이 확인하면 요청과 지원이 모두 `ALL_COMPLETED`가 된다 | `test_proposal_integration.py::test_confirm_received_after_runner_completion_marks_both_all_completed` |
| PROPOSAL-TS-017 | 양측 임무 완료 시 행님·꼬붕에게 임무 수행 완료 알림이 생긴다 | `test_proposal_integration.py::test_confirm_received_after_runner_completion_creates_execution_completed_notifications` |
| PROPOSAL-TS-018 | 행님 분쟁 접수는 요청과 지원을 `DISPUTED`로 바꾸고 시각을 기록한다 | `test_proposal_integration.py::test_raise_proposal_dispute_updates_both_statuses_and_timestamps` |
| PROPOSAL-TS-019 | 행님 분쟁 접수는 누락·비활성·대상 불일치 설문 질문을 거부한다 | `test_proposal_integration.py::test_raise_proposal_dispute_rejects_invalid_survey_question` |
| PROPOSAL-TS-020 | 행님 분쟁 사유는 필수이고 기타 사유일 때만 상세 사유가 필수다 | `test_proposal_integration.py::test_raise_proposal_dispute_requires_detail_only_for_etc_reason` |
| PROPOSAL-TS-021 | 행님 분쟁은 기타 사유와 상세 사유를 함께 받으면 접수된다 | `test_proposal_integration.py::test_raise_proposal_dispute_accepts_etc_reason_with_detail` |
| PROPOSAL-TS-022 | `ALL_COMPLETED` 요청은 행님 분쟁 접수를 거부하고 상태를 유지한다 | `test_proposal_integration.py::test_raise_proposal_dispute_rejects_all_completed` |
| PROPOSAL-TS-023 | 요청 ORM 모델이 문서화된 필드와 enum 정책을 지킨다 | `test_proposal_integration.py::test_proposal_model_contract` |
| PROPOSAL-TS-024 | 게시글 신고 사유 목록은 활성 사유만 표시 순서대로 반환한다 | `test_proposal_report_integration.py::test_list_proposal_report_reasons_returns_active_ordered_questions` |
| PROPOSAL-TS-025 | 게시글 신고는 공개 요청·다른 사용자·사용자당 1건 규칙을 검증한다 | `test_proposal_report_integration.py::test_create_proposal_report_validates_public_target_reporter_and_duplicate` |
| PROPOSAL-TS-026 | 게시글 신고 사유는 필수이고 기타 사유일 때만 상세 사유가 필수다 | `test_proposal_report_integration.py::test_create_proposal_report_requires_detail_only_for_etc_reason` |
| PROPOSAL-TS-027 | 신고 승인은 요청을 `REPORTED`로 바꾸고 대기 지원을 거절한다 | `test_proposal_report_integration.py::test_accept_proposal_report_marks_proposal_reported_and_rejects_waiting_offers` |
| PROPOSAL-TS-028 | 관리자는 신고를 반려할 수 있고 처리한 신고는 다시 처리할 수 없다 | `test_proposal_report_integration.py::test_admin_can_reject_report_and_cannot_review_report_twice` |
| PROPOSAL-TS-029 | 관리자 신고 조회는 신고자 이름을 내려준다 | `test_proposal_report_integration.py::test_admin_report_views_expose_reporter_name` |
| PROPOSAL-TS-030 | 앱의 신고 생성 응답은 신고자 이름을 채우지 않는다 | `test_proposal_report_integration.py::test_report_creation_response_omits_reporter_name` |
