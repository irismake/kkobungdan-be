# Chat Test Scenarios

> 상태: 구현 전 (모든 시나리오가 아직 테스트로 작성되지 않음)
> 요구사항 정본: [`chat-requirements.md`](../../product-specs/chat-requirements.md) (`CHAT-REQ-*`)

기준 테스트 파일: `tests/test_chat_service.py`(단위), `tests/test_chat_integration.py`(통합), `tests/test_chat_realtime_integration.py`(실시간 연결 통합, 예정)

## 시나리오

각 시나리오는 테스트와 1:1로 연결한다. 연결 방식은 [`../../design-docs/tdd-workflow.md`](../../design-docs/tdd-workflow.md)를 따른다.

- 테스트 위치 약어: `service` = `tests/test_chat_service.py`(단위), `api` = `tests/test_chat_integration.py`(통합), `realtime` = `tests/test_chat_realtime_integration.py`(실시간 연결 통합)
- 푸시는 기존 테스트처럼 가짜 FCM 발송기로 발송 내용을 확인한다.
- **(차단 후)** 표시는 차단 구현([`user-block.md`](../../product-specs/user-block.md)) 뒤에 활성화한다. 그 전에는 skip으로 둔다.
- **(동시)** 표시는 두 요청을 동시에 보내 결과를 확인하는 테스트다.
- 공통 Outbox 동작(발행 재시도, 전달 중복 방지, DEAD 재처리, 정리)은 [`../outbox/test-scenarios.md`](../outbox/test-scenarios.md)(`OUTBOX-TS-*`)에서 확인한다. CHAT-TS-102~104, 107~109는 그 문서로 옮겼고 번호는 비워 둔다.
- 앱이 지켜야 하는 규칙(채팅 ID로 중복 표시 제거, 오래된 이벤트 무시, 앱이 켜져 있을 때 푸시 표시 방식)은 서버 테스트 대상이 아니다. 서버는 그 규칙에 필요한 값(채팅 ID, 이벤트 순서 값)을 내려주는지만 검증한다.

| ID | 요구사항 | 시나리오 (Given / When / Then) | 종류 | 테스트 위치 |
|----|----------|-------------------------------|------|-------------|
| CHAT-TS-001 | CHAT-REQ-001 | Given 게시된 요청 / When 꼬붕이 지원 / Then 채팅방 1개가 `ACTIVE`로 생기고 참여자는 행님과 그 꼬붕 2명이다 | integration | `api` |
| CHAT-TS-002 | CHAT-REQ-001 | Given 게시된 요청 / When 꼬붕 A와 B가 각각 지원 / Then 꼬붕별로 채팅방이 따로 생기고 서로의 채팅이 섞이지 않는다 | integration | `api` |
| CHAT-TS-003 | CHAT-REQ-001 | Given 같은 행님의 요청 2개 / When 같은 꼬붕이 둘 다 지원 / Then 채팅방이 2개 생긴다 | integration | `api` |
| CHAT-TS-004 | CHAT-REQ-002 | Given 채팅방 / When 참여자가 아닌 사용자가 채팅방이나 채팅 내역을 조회 / Then `403 FORBIDDEN` | integration | `api` |
| CHAT-TS-005 | CHAT-REQ-002 | Given 꼬붕 A·B가 지원한 요청 / When 행님이 두 채팅방을, 꼬붕 B가 A의 채팅방을 조회 / Then 행님은 둘 다 조회되고 꼬붕 B는 `403` | integration | `api` |
| CHAT-TS-006 | CHAT-REQ-002 | Given `CLOSED`가 된 채팅방 / When 참여자가 조회 / Then 조회된다 | integration | `api` |
| CHAT-TS-007 | CHAT-REQ-002 | Given 채팅이 있는 채팅방 / When 관리자가 관리자 웹 API로 조회하고 채팅 전송을 시도 / Then 조회는 되고 전송은 거부되며 참여자의 읽음 위치는 바뀌지 않는다 | integration | `api` |
| CHAT-TS-008 | CHAT-REQ-003 | Given `ACTIVE` 채팅방 / When 참여자가 텍스트 채팅을 전송 / Then 발신자·내용·UTC 전송 시각과 함께 저장되고 응답된다 | integration | `api` |
| CHAT-TS-009 | CHAT-REQ-003, CHAT-REQ-006 | Given 결합 이모지를 포함한 내용 / When 글자 수를 검증 / Then 화면 글자(grapheme) 기준으로 500자는 통과하고 501자는 거부된다 | unit | `service` |
| CHAT-TS-010 | CHAT-REQ-004 | Given 채팅 45개가 있는 채팅방 / When 처음 조회한 뒤 이전 채팅을 추가 조회 / Then 처음엔 최근 30개, 다음엔 나머지 15개가 저장 순서대로 온다 | integration | `api` |
| CHAT-TS-011 | CHAT-REQ-014 | Given 마지막 채팅 시각이 다른 채팅방 2개와 채팅이 없는 채팅방 1개 / When 채팅 목록 조회 / Then 마지막 채팅이 최신인 순서이고 채팅 없는 방은 생성 시각으로 정렬된다 | integration | `api` |
| CHAT-TS-012 | CHAT-REQ-014 | Given 채팅방 / When 채팅 목록 조회 / Then 각 항목에 상대 이름, 요청 제목, 마지막 채팅, 마지막 채팅 시각, 안읽음 수, 채팅방 상태, `statusReason`, 요청·지원 상태, 차단 여부가 있다 **(차단 후: 차단 여부)** | integration | `api` |
| CHAT-TS-013 | CHAT-REQ-014, CHAT-REQ-005 | Given 상대가 회원 탈퇴한 채팅방 / When 목록과 채팅 내역을 조회 / Then 이름은 `"탈퇴한 사용자"`이고 그 사람이 보낸 채팅 내용은 그대로다 | integration | `api` |
| CHAT-TS-014 | CHAT-REQ-014, CHAT-REQ-010 | Given 안읽은 채팅이 있는 채팅방 / When 채팅 목록만 조회 / Then 읽음 위치와 안읽음 수가 바뀌지 않는다 | integration | `api` |
| CHAT-TS-015 | CHAT-REQ-005 | Given 채팅이 있는 채팅방 / When 채팅방이 `CLOSED`가 되거나 한쪽이 차단 / Then 양쪽 모두 기존 채팅을 조회할 수 있다 **(차단 후: 차단 경우)** | integration | `api` |
| CHAT-TS-016 | CHAT-REQ-006, CHAT-REQ-021 | Given 게시된 요청 / When 꼬붕이 첫 인사와 함께 지원 / Then 채팅 시작 안내, 첫 인사(꼬붕의 일반 채팅) 순서로 저장된다 | integration | `api` |
| CHAT-TS-017 | CHAT-REQ-006, CHAT-REQ-023 | Given 게시된 요청 / When 첫 인사 없이, 공백만으로, 또는 501자로 지원 / Then 지원이 거부되고 지원·채팅방·채팅이 하나도 남지 않는다 | integration | `api` |
| CHAT-TS-018 | CHAT-REQ-007 | Given 꼬붕 A·B가 지원한 요청 / When 행님이 A를 매칭 / Then A 채팅방은 `ACTIVE`, B 채팅방은 `CLOSED`·`NOT_SELECTED` | integration | `api` |
| CHAT-TS-019 | CHAT-REQ-007 | Given 대기 중인 지원 / When 꼬붕이 지원을 취소하거나 회원 탈퇴 / Then 채팅방이 `CLOSED`·`OFFER_CANCELLED` | integration | `api` |
| CHAT-TS-020 | CHAT-REQ-007 | Given 지원이 2건 있는 요청 / When 행님이 매칭 전에 요청을 취소 / Then 두 채팅방 모두 `CLOSED`·`PROPOSAL_CANCELLED` | integration | `api` |
| CHAT-TS-021 | CHAT-REQ-007 | Given 매칭 전 요청과 매칭 후 요청 / When 관리자가 각각 취소 / Then `CLOSED`가 아니던 채팅방이 `CLOSED`·`ADMIN_CANCELLED` | integration | `api` |
| CHAT-TS-022 | CHAT-REQ-007, CHAT-REQ-021 | Given 대기 지원이 있는 신고된 요청 / When 관리자가 신고를 승인 / Then 대기 지원 채팅방이 `CLOSED`·`ADMIN_CANCELLED`이고 시스템 채팅은 생기지 않는다 | integration | `api` |
| CHAT-TS-023 | CHAT-REQ-007 | Given 진행 중인 임무 / When 행님 또는 꼬붕이 분쟁 접수 후 관리자가 판정 / Then 접수 시 `INACTIVE`·`ORDERER_DISPUTED` 또는 `RUNNER_DISPUTED`, 판정 시 `CLOSED`·`DISPUTE_COMPLETED` 또는 `DISPUTE_FAILED` | integration | `api` |
| CHAT-TS-024 | CHAT-REQ-007 | Given 이벤트(매칭, 미선정, 취소, 분쟁, 판정, 양측 확인) / When 채팅방 상태 변경 규칙에 넣음 / Then [상태 이유](../../product-specs/chat-requirements.md#상태-이유-statusreason) 표와 같은 상태와 `statusReason`이 나온다 | unit | `service` |
| CHAT-TS-025 | CHAT-REQ-008 | Given 진행 중인 임무 / When 한쪽만 임무 완료(확인), 이어서 다른 쪽도 /  Then 첫 확인 뒤에는 `ACTIVE`, 두 번째 확인 뒤에는 `CLOSED`·`ALL_CONFIRMED` | integration | `api` |
| CHAT-TS-026 | CHAT-REQ-008 | Given 이미 임무 완료(확인)를 한 사용자 / When 다시 요청 / Then 오류로 거부되고 채팅방 상태와 시스템 채팅이 바뀌지 않는다 | integration | `api` |
| CHAT-TS-027 | CHAT-REQ-008 | Given 한쪽이 상대를 차단한 진행 중 임무 / When 임무 완료(확인) / Then 처리된다 **(차단 후)** | integration | `api` |
| CHAT-TS-028 | CHAT-REQ-009 | Given `INACTIVE` 또는 `CLOSED` 채팅방 / When 채팅 전송 / Then 거부되고 채팅이 저장되지 않는다 | integration | `api` |
| CHAT-TS-029 | CHAT-REQ-009 | Given 한쪽이 차단한 `ACTIVE` 채팅방 / When 양쪽이 각각 전송 / Then 둘 다 거부된다 **(차단 후)** | integration | `api` |
| CHAT-TS-030 | CHAT-REQ-010 | Given 안읽은 채팅 3개 / When 채팅방에 들어감 / Then 그 시점의 마지막 채팅까지 읽음 처리되고 안읽음 수가 0 | integration | `api` |
| CHAT-TS-031 | CHAT-REQ-010 | Given 상대 채팅 2개를 읽지 않은 상태 / When 내가 채팅을 전송 / Then 내 채팅 앞의 채팅까지 읽음 처리된다 | integration | `api` |
| CHAT-TS-032 | CHAT-REQ-010 | Given 읽음 위치가 채팅 10 / When 채팅 7로 읽음 요청 / Then 성공 응답이고 읽음 위치는 10으로 유지된다 | unit | `service` |
| CHAT-TS-033 | CHAT-REQ-010 | Given 채팅방 A / When 채팅방 B의 채팅이나 없는 채팅으로 읽음 요청 / Then 거부된다 | integration | `api` |
| CHAT-TS-034 | CHAT-REQ-010 | Given `CLOSED` 채팅방과 차단된 채팅방 / When 읽음 요청 / Then 읽음 처리된다 **(차단 후: 차단 경우)** | integration | `api` |
| CHAT-TS-035 | CHAT-REQ-011 | Given 읽음 위치 이후 내 채팅 1, 상대 채팅 2, 시스템 채팅 1, 행님용 미선정 안내 1 / When 안읽음 수 계산 / Then 3 (행님 기준 미선정 안내 제외) | unit | `service` |
| CHAT-TS-036 | CHAT-REQ-011, CHAT-REQ-006 | Given 게시된 요청 / When 꼬붕이 첫 인사와 함께 지원 / Then 행님의 그 채팅방 안읽음 수는 2(채팅 시작 안내, 첫 인사), 꼬붕은 1(채팅 시작 안내) | integration | `api` |
| CHAT-TS-037 | CHAT-REQ-011 | Given 안읽은 채팅이 있는 `ACTIVE`·`CLOSED`·차단 채팅방 / When 안읽음 수 조회 / Then 채팅방별 수와 그 합계가 오고 `CLOSED`·차단 방도 합계에 포함된다 **(차단 후: 차단 경우)** | integration | `api` |
| CHAT-TS-038 | CHAT-REQ-012 | Given 행님·꼬붕 역할이 섞인 채팅방 3개(`CLOSED`, 차단 채팅방 포함) / When 전체 읽음 / Then 모두 요청 시점까지 읽음 처리되고 상대방의 읽음 위치는 바뀌지 않는다 **(차단 후: 차단 경우)** | integration | `api` |
| CHAT-TS-039 | CHAT-REQ-012 | Given 전체 읽음 요청 시점의 마지막 채팅이 채팅 10인데, 사용자가 그 사이 채팅방에 들어가 채팅 11까지 읽음 / When 전체 읽음이 처리 / Then 그 채팅방의 읽음 위치는 채팅 11로 유지된다 | unit | `service` |
| CHAT-TS-040 | CHAT-REQ-013 | Given 내가 보낸 채팅 3개 / When 상대가 2번째까지 읽은 뒤 채팅방 조회 / Then 응답에 상대의 마지막 읽은 채팅(2번째)이 담긴다 | integration | `api` |
| CHAT-TS-041 | CHAT-REQ-015 | Given 채팅방 A·B에 참여하고 실시간 연결된 사용자 / When 두 방에 각각 상대가 채팅 / Then 하나의 연결로 두 채팅을 모두 받는다 | integration | `realtime` |
| CHAT-TS-042 | CHAT-REQ-015 | Given 참여자가 아닌 사용자의 실시간 연결 / When 채팅방에 새 채팅 / Then 그 사용자는 받지 않는다 | integration | `realtime` |
| CHAT-TS-043 | CHAT-REQ-015 | Given 실시간 연결된 상대 / When 채팅 저장이 실패 / Then 실시간 전달도 없다 | integration | `realtime` |
| CHAT-TS-044 | CHAT-REQ-015, CHAT-REQ-028 | Given 실시간 연결 / When 채팅을 받음 / Then 이벤트에 채팅 ID와 채팅방 ID가 있다 | integration | `realtime` |
| CHAT-TS-045 | CHAT-REQ-016, CHAT-REQ-024 | Given 앱이 채팅 10까지 받은 뒤 채팅 11~15가 저장 / When 채팅 10 이후를 조회 / Then 11~15가 빠짐·중복 없이 저장 순서대로 온다 | integration | `api` |
| CHAT-TS-046 | CHAT-REQ-016 | Given 만료된 access token / When 실시간 연결 / Then 거부된다 | integration | `realtime` |
| CHAT-TS-047 | CHAT-REQ-016 | Given 실시간 연결 중 / When access token이 만료 / Then 서버가 연결을 끊는다 | integration | `realtime` |
| CHAT-TS-048 | CHAT-REQ-017 | Given 꼬붕 A·B가 실시간 연결된 요청 / When 행님이 A를 매칭 / Then A·B와 행님이 각자 채팅방 상태·`statusReason`·요청·지원 상태 변경 이벤트를 받는다 | integration | `realtime` |
| CHAT-TS-049 | CHAT-REQ-017, CHAT-REQ-013 | Given 실시간 연결된 두 참여자 / When 한쪽이 읽음 처리 / Then 상대는 읽음 위치 변경 이벤트를, 읽은 쪽은 안읽음 수·합계 변경 이벤트를 받는다 | integration | `realtime` |
| CHAT-TS-050 | CHAT-REQ-017 | Given 실시간 연결된 두 참여자 / When 한쪽이 차단 후 해제 / Then 양쪽이 차단 상태 변경 이벤트를 두 번 받는다 **(차단 후)** | integration | `realtime` |
| CHAT-TS-051 | CHAT-REQ-018 | Given 채팅방 / When 상대가 채팅 전송 (실시간 연결 여부와 무관) / Then 받는 사람에게 제목=상대 이름, 내용=채팅 내용, 배지=채팅 안읽음 합계+알림 미읽음 수인 푸시가 1번 간다 | integration | `api` |
| CHAT-TS-052 | CHAT-REQ-018 | Given 채팅방 / When 내가 채팅을 보내거나, 받는 사람의 `alarm_enabled`가 꺼져 있음 / Then 나에게는 푸시가 없고, 알림이 꺼진 사람은 푸시 없이 안읽음 수만 늘어난다 | integration | `api` |
| CHAT-TS-053 | CHAT-REQ-018 | Given 같은 채팅방 / When 상대가 채팅을 연속 2개 전송 / Then 두 푸시가 같은 채팅방 묶음 키를 쓰고, 탭하면 그 채팅방으로 이동하는 값이 담긴다 | integration | `api` |
| CHAT-TS-054 | CHAT-REQ-018 | Given 채팅방 / When 채팅 푸시 발송 / Then `notifications`에 레코드가 생기지 않는다 | integration | `api` |
| CHAT-TS-055 | CHAT-REQ-018 | Given 채팅 안읽음 3, 알림 미읽음 2인 사용자 / When 기존 도메인 알림 푸시 발송 / Then 배지가 5다 | integration | `tests/test_notification_integration.py` |
| CHAT-TS-056 | CHAT-REQ-019 | Given 채팅방 / When 같은 전송 ID로 같은 채팅을 두 번 전송 / Then 채팅은 1개, 두 응답이 같은 채팅이고 푸시와 실시간 전달은 1번이다 | integration | `api` |
| CHAT-TS-057 | CHAT-REQ-019 | Given 전송 ID X로 저장된 채팅 / When 같은 ID로 내용이나 채팅방이 다른 요청 / Then 거부된다 | integration | `api` |
| CHAT-TS-058 | CHAT-REQ-020 | Given 시스템 채팅을 만드는 사건 / When 사건 처리가 중간에 실패해 롤백 / Then 시스템 채팅도 남지 않는다 | integration | `api` |
| CHAT-TS-059 | CHAT-REQ-020 | Given 입금 완료 사건 / When 같은 사건이 두 번 처리 / Then 시스템 채팅은 1개다 | integration | `api` |
| CHAT-TS-060 | CHAT-REQ-020 | Given `CLOSED` 채팅방, 차단된 채팅방 / When 입금·환불 완료 / Then 시스템 채팅이 저장된다 **(차단 후: 차단 경우)** | integration | `api` |
| CHAT-TS-061 | CHAT-REQ-020 | Given 채팅 전송 API / When 사용자가 채팅 유형(시스템 채팅) 필드를 담아 전송 / Then `400 VALIDATION_ERROR`로 거부되고 채팅이 저장되지 않는다 | integration | `api` |
| CHAT-TS-062 | CHAT-REQ-021 | Given [사건별 시스템 채팅](../../product-specs/chat-requirements.md#chat-req-021--사건별-시스템-채팅) 표의 각 사건과 받는 사람 / When 문구를 고름 / Then 표의 문구가 나온다 | unit | `service` |
| CHAT-TS-063 | CHAT-REQ-021, CHAT-REQ-018 | Given 표의 각 사건과 받는 사람 / When 안읽음 포함 여부와 푸시 대상을 고름 / Then 표의 "기존 알림"·"안읽음·푸시" 칸과 같다 | unit | `service` |
| CHAT-TS-064 | CHAT-REQ-021 | Given 매칭 전 요청과 매칭 후 요청 / When 관리자가 각각 취소 / Then 매칭 전은 "요청이 취소되어 채팅이 종료됐어요.", 매칭 후는 "종료된 임무예요. 더 이상 진행할 수 없어요." | integration | `api` |
| CHAT-TS-065 | CHAT-REQ-021 | Given 매칭 후 분쟁 판정 꼬붕 책임 요청과 매칭 전 취소 요청 / When 각각 환불 완료 / Then 매칭 후 요청의 채팅방에만 환불 완료 안내가 생긴다 | integration | `api` |
| CHAT-TS-066 | CHAT-REQ-021 | Given 수행비 15,000원 임무 / When 입금 완료 / Then 안내에 "15,000원"이 들어가고 행님·꼬붕 모두 본다 | integration | `api` |
| CHAT-TS-067 | CHAT-REQ-022 | Given 일반 채팅과 시스템 채팅이 섞인 채팅방 / When 채팅 내역 조회 / Then 한 목록에서 저장 순서대로 오고 시스템 채팅은 구분된다 | integration | `api` |
| CHAT-TS-068 | CHAT-REQ-023 | Given 게시된 요청 / When 같은 꼬붕이 지원을 동시에 2번 요청 **(동시)** / Then 지원, 채팅방, 채팅 시작 안내, 첫 인사가 각각 1개다 | integration | `api` |
| CHAT-TS-069 | CHAT-REQ-023 | Given 채팅방이 없는 기존 지원들 / When 배포용 채팅방 생성 작업을 두 번 실행 / Then 지원마다 채팅방이 1개이고, 상태는 지원 상태에 맞으며, 시스템 채팅은 생기지 않는다 | integration | `api` |
| CHAT-TS-070 | CHAT-REQ-024 | Given 같은 채팅방 / When 두 참여자가 채팅을 동시에 여러 개 전송 **(동시)** / Then 모든 채팅이 서로 다른 순서를 갖고, 마지막으로 받은 채팅 이후 조회에서 빠지는 채팅이 없다 | integration | `api` |
| CHAT-TS-071 | CHAT-REQ-024, CHAT-REQ-025 | Given `ACTIVE` 채팅방 / When 채팅 전송과 채팅방 종료(지원 취소)가 동시에 일어남 **(동시)** / Then 채팅은 거부되거나 종료 안내보다 앞에 저장되며, 종료 안내 뒤에 일반 채팅이 없다 | integration | `api` |
| CHAT-TS-072 | CHAT-REQ-026 | Given 꼬붕 A·B가 지원한 요청 / When 행님이 A와 B를 동시에 매칭 **(동시)** / Then 한 명만 매칭되고 `ACTIVE` 채팅방은 1개다 | integration | `api` |
| CHAT-TS-073 | CHAT-REQ-026 | Given 대기 중인 지원 / When 매칭과 꼬붕의 지원 취소가 동시에 일어남 **(동시)** / Then 둘 중 하나만 확정되고 그 채팅방에 매칭 안내와 지원 취소 안내가 함께 있지 않다 | integration | `api` |
| CHAT-TS-074 | CHAT-REQ-026 | Given 진행 중인 임무 / When 꼬붕의 임무 완료와 행님의 임무 완료 확인이 동시에 **(동시)** / Then 채팅방은 한 번 `CLOSED`가 되고 양측 임무 완료 안내는 1개다 | integration | `api` |
| CHAT-TS-075 | CHAT-REQ-026 | Given `CLOSED` 채팅방 / When 늦게 도착한 분쟁 접수나 상태 변경 요청 / Then 채팅방은 `ACTIVE`나 `INACTIVE`로 돌아가지 않는다 | integration | `api` |
| CHAT-TS-076 | CHAT-REQ-027 | Given 채팅 10개 / When 같은 사용자가 채팅 5와 채팅 9로 동시에 읽음 요청 **(동시)** / Then 읽음 위치는 채팅 9다 | integration | `api` |
| CHAT-TS-077 | CHAT-REQ-027 | Given 읽음 요청이 채팅 9를 가리킴 / When 그 사이 채팅 10이 저장된 뒤 읽음이 처리 / Then 채팅 10은 안읽음으로 남는다 | integration | `api` |
| CHAT-TS-078 | CHAT-REQ-028 | Given 실시간 연결 / When 같은 채팅방의 상태·읽음 이벤트가 여러 번 발생 / Then 각 이벤트에 순서 값이 있고 발생 순서대로 커진다 | integration | `realtime` |
| CHAT-TS-079 | CHAT-REQ-018, CHAT-REQ-029 | Given 첫 시도에 실패하고 두 번째에 성공하는 가짜 FCM 발송기 / When 상대가 채팅 전송 후 재시도 처리 / Then 채팅 전송 응답은 성공이고, 푸시는 두 번째 시도에 성공해 성공 기준 1번만 나간다 | integration | `api` |
| CHAT-TS-080 | CHAT-REQ-003, CHAT-REQ-006 | Given 빈 문자열, 공백만, 줄바꿈만, 공백과 줄바꿈이 섞인 내용 / When 채팅·첫 인사 내용을 검증 / Then 모두 거부되고, 앞뒤에 공백이 있어도 글자가 하나라도 있으면 통과한다 | unit | `service` |
| CHAT-TS-081 | CHAT-REQ-002, CHAT-REQ-003 | Given 채팅방 / When 참여자가 아닌 사용자가 채팅 전송 / Then `403 FORBIDDEN`이고 채팅이 저장되지 않는다 | integration | `api` |
| CHAT-TS-082 | CHAT-REQ-014 | Given 마지막 채팅이 시스템 채팅(매칭 미선정)인 채팅방 / When 꼬붕과 행님이 각각 채팅 목록 조회 / Then 마지막 채팅에 각자에게 보이는 시스템 채팅 문구가 나온다 | integration | `api` |
| CHAT-TS-083 | CHAT-REQ-014 | Given 행님으로 참여한 채팅방과 꼬붕으로 참여한 채팅방이 섞여 한 페이지보다 많음 / When 채팅 목록을 처음 조회한 뒤 이전 목록을 추가 조회 / Then 두 역할의 채팅방이 모두 나오고 빠지거나 겹치는 채팅방이 없다 | integration | `api` |
| CHAT-TS-084 | CHAT-REQ-015, CHAT-REQ-022 | Given 실시간 연결된 두 참여자 / When 지원 취소로 시스템 채팅이 저장 / Then 양쪽이 각자에게 보이는 문구의 시스템 채팅을 실시간으로 받는다 | integration | `realtime` |
| CHAT-TS-085 | CHAT-REQ-016 | Given `CLOSED`·`INACTIVE` 채팅방에서 앱이 채팅 5까지 받은 뒤 시스템 채팅이 저장 / When 채팅 5 이후를 조회 / Then 놓친 채팅이 저장 순서대로 온다 | integration | `api` |
| CHAT-TS-086 | CHAT-REQ-017 | Given 실시간 연결된 두 참여자의 진행 중 임무 / When 꼬붕이 임무 완료 / Then 양쪽이 지원 상태와 임무 완료 확인 여부 변경 이벤트를 받는다 | integration | `realtime` |
| CHAT-TS-087 | CHAT-REQ-007 | Given 분쟁 중인 요청 / When 관리자가 요청 취소 / Then 취소가 거부되고 채팅방은 `INACTIVE`를 유지하며 시스템 채팅이 생기지 않는다 | integration | `api` |
| CHAT-TS-088 | CHAT-REQ-006, CHAT-REQ-023 | Given 게시된 요청 / When 지원 등록 중 첫 인사 저장이 실패 / Then 지원, 채팅방, 지원 등록 안내가 하나도 남지 않는다 | integration | `api` |
| CHAT-TS-089 | CHAT-REQ-021 | Given [사건별 시스템 채팅](../../product-specs/chat-requirements.md#chat-req-021--사건별-시스템-채팅) 표의 각 사건 / When 실제 API로 그 사건을 일으킴 / Then 표의 채팅방에 시스템 채팅이 1개 저장되고, 행님·꼬붕이 각자 조회하면 표의 문구가 나온다 | integration | `api` |
| CHAT-TS-090 | CHAT-REQ-021 | Given 매칭 후 환불 대상이 된 요청 / When 환불이 `PENDING`으로 생성된 뒤 `COMPLETED`가 됨 / Then `PENDING`일 때는 환불 안내가 없고 `COMPLETED`가 된 뒤 1개 생긴다 | integration | `api` |
| CHAT-TS-091 | CHAT-REQ-018, CHAT-REQ-021 | Given 대기 중인 지원 / When 꼬붕이 지원을 취소 / Then 행님에게 제목=꼬붕 이름, 내용="꼬붕이 지원을 취소했어요. 채팅이 자동으로 종료돼요."인 푸시가 가고, 꼬붕에게는 꼬붕용 문구의 푸시가 간다 | integration | `api` |
| CHAT-TS-092 | CHAT-REQ-018, CHAT-REQ-021 | Given 진행 중인 임무 / When 꼬붕이 임무 완료 / Then 행님은 기존 알림 푸시만 받고 시스템 채팅 푸시는 받지 않으며, 행님의 안읽음 수는 1 늘어난다 | integration | `api` |
| CHAT-TS-093 | CHAT-REQ-024 | Given 진행 중인 임무 / When 꼬붕 임무 완료, 행님 임무 완료 확인, 수행비 입금 완료가 차례로 일어남 / Then 시스템 채팅이 한쪽 임무 완료, 양측 임무 완료, 입금 완료 순서로 저장된다 | integration | `api` |
| CHAT-TS-094 | CHAT-REQ-025 | Given `ACTIVE` 채팅방이 지원 취소로 `CLOSED`가 됨 / When 앱이 이전 상태를 기준으로 채팅 전송 / Then 전송 불가 에러 코드로 거부되고, 채팅방을 조회하면 `CLOSED`·`OFFER_CANCELLED`가 나온다 | integration | `api` |
| CHAT-TS-095 | CHAT-REQ-026 | Given 대기 중인 지원 / When 매칭과 행님의 요청 취소, 매칭과 관리자 취소가 각각 동시에 일어남 **(동시)** / Then 각 경우 둘 중 하나만 확정되고 채팅방 상태와 시스템 채팅은 확정된 쪽만 따른다 | integration | `api` |
| CHAT-TS-096 | CHAT-REQ-026 | Given 진행 중인 임무 / When 임무 완료와 분쟁 접수가 동시에 일어남 **(동시)** / Then 먼저 확정된 쪽만 반영되고, 뒤의 동작은 바뀐 상태에서 허용될 때만 처리된다 | integration | `api` |
| CHAT-TS-097 | CHAT-REQ-027, CHAT-REQ-012 | Given 채팅 10개가 있는 채팅방 / When 전체 읽음 처리 중에 채팅 11이 저장됨 **(동시)** / Then 채팅 11은 안읽음으로 남는다 | integration | `api` |
| CHAT-TS-098 | CHAT-REQ-019 | Given 채팅방 / When 행님과 꼬붕이 우연히 같은 전송 ID로 각각 전송 / Then 두 채팅이 모두 저장된다 (중복 판단은 사용자별) | integration | `api` |
| CHAT-TS-099 | CHAT-REQ-023 | Given 배포용 채팅방 생성 작업이 실행 중 / When 새 지원이 등록됨 **(동시)** / Then 새 지원의 채팅방은 1개이고 지원 등록 안내와 첫 인사가 있다 | integration | `api` |
| CHAT-TS-100 | CHAT-REQ-029 | Given `ACTIVE` 채팅방 / When 채팅 전송이 커밋됨, 또는 같은 처리 중 오류로 롤백됨 / Then 커밋된 경우에만 `chat.message.created` 이벤트가 outbox에 1개 남고, 롤백되면 채팅과 이벤트 모두 없다 | integration | `api` |
| CHAT-TS-101 | CHAT-REQ-029, CHAT-REQ-020 | Given 대기 중인 지원 / When 지원 취소 처리 중 시스템 채팅 저장 뒤에 오류로 롤백됨 / Then 지원 상태, 채팅방 상태, 시스템 채팅, outbox 이벤트가 모두 남지 않는다 | integration | `api` |
| CHAT-TS-105 | CHAT-REQ-029 | Given 채팅 전송 이벤트의 실시간 전달은 성공하고 푸시는 실패 / When 재시도 처리 / Then 푸시만 다시 시도되고 실시간 이벤트는 다시 보내지 않는다 | integration | `api` |
| CHAT-TS-106 | CHAT-REQ-018, CHAT-REQ-029 | Given 저장된 지 10분이 지난 채팅의 실패한 푸시 / When 재시도 처리 / Then 보내지 않고 `SKIPPED`로 끝낸다 | unit | `service` |
| CHAT-TS-110 | CHAT-REQ-029, CHAT-REQ-016 | Given 받는 사람이 연결되어 있지 않거나 WebSocket 전송이 오류를 냄 / When `chat.realtime`이 이벤트를 처리 / Then `SKIPPED`로 끝나고 다시 시도하지 않으며 모니터링 알림도 없다 | unit | `service` |
| CHAT-TS-111 | CHAT-REQ-018, CHAT-REQ-029 | Given 계속 실패하는 가짜 FCM 발송기 / When `chat.push`가 재시도를 반복 / Then 5초, 30초, 1분, 2분, 4분 간격으로 5회 재시도하고 모두 10분 안에 끝나며, 그 뒤 `DEAD`가 되어 모니터링 알림이 1번 나간다 | unit | `service` |
