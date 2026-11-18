# 채팅 구현

> 상태: 진행 중 (설계 완료, 구현 전)
> 요구사항: [`../../product-specs/chat-requirements.md`](../../product-specs/chat-requirements.md) · 시나리오: [`../../domains/chat/test-scenarios.md`](../../domains/chat/test-scenarios.md) · 설계: [`../../design-docs/chat-architecture.md`](../../design-docs/chat-architecture.md)
> 브랜치: `feature/chat` (PR #8)

## 목표

카카오톡 오픈채팅방을 앱 내 채팅으로 대체한다. [TDD 흐름](../../design-docs/tdd-workflow.md)대로 시나리오마다 실패하는 테스트를 먼저 쓰고(Red) 구현한다(Green).

## 진행 단계

1. [x] 요구사항과 정책 정의 (`CHAT-REQ-001~029`, 공통 `OUTBOX-REQ-001~008`, 차단·신고 정책 문서)
2. [x] 테스트 시나리오 작성 (`CHAT-TS-001~111` 105개, 공통 `OUTBOX-TS-001~021`)
3. [x] 서버 아키텍처 설계 (`chat-architecture.md`, 공통 `outbox.md`)
4. [ ] TDD 구현: 아래 묶음 순서대로
5. [ ] 전체 CI 검증, PR Ready for review, staging 머지와 배포 확인

## 4단계 구현 묶음

각 묶음은 Red 커밋(`test:`, 시나리오 테스트 추가) → Green 커밋(`feat:`/`fix:`) → 필요하면 Refactor 커밋으로 진행한다. 묶음이 끝날 때마다 `scripts/verify.sh`가 통과해야 한다. 차단 관련 시나리오(**차단 후**)는 테스트를 쓰고 `skip(reason="사용자 차단 구현 후 활성화")`으로 둔다.

| 순서 | 묶음 | 요구사항 | 시나리오 (CHAT-TS-) | 주요 변경 |
|------|------|----------|---------------------|-----------|
| 4-1 | 채팅방 생성·첫 인사·접근 권한 | 001, 002, 006 | 001~006, 009, 016, 017, 080, 088 | `chat_rooms`·`chat_messages` 모델과 Alembic 마이그레이션, `OfferCreate.greeting`, `ChatLifecycle.on_offer_created`, 채팅방 상세 API, 권한 검사 |
| 4-2 | Transactional Outbox (공통) | OUTBOX-REQ-001~008 | OUTBOX-TS-001~021 | [`outbox.md`](../../design-docs/outbox.md) 전부: 모델·마이그레이션, `record_event`, 봉투, 발행자(프로세스 내), relay(`SKIP LOCKED`, 발행 재시도), 전달 처리(임대·재시도·SKIPPED·DEAD), 지연·DEAD 알림, 관리자 재처리 API, 정리 배치, 스케줄러 등록 |
| 4-3 | 채팅 전송·조회·목록 | 003, 004, 005, 014, 019, 029 | 008, 010~015, 045, 056, 057, 061, 067, 081~083, 098, 100 | 전송(순번·중복 방지, outbox 기록), 이전·이후 조회, 목록(정렬·커서), 탈퇴 사용자 표시 |
| 4-4 | 채팅방 상태와 시스템 채팅 | 007, 008, 009, 020, 021, 022, 029 | 018~029, 058~060, 062~066, 087, 089, 090, 093, 094, 101 | `system_chat.py` 문구 표, 기존 서비스의 `ChatLifecycle` 호출(설계 문서 호출 지점 표), 전송 제한 |
| 4-5 | 읽음과 안읽음 | 010~013 | 030~040 | 읽음(뒤로만), 전체 읽음, 안읽음 계산과 합계, 상대 읽음 위치 |
| 4-6 | 채팅 푸시 | 018, 029 | 051~055, 079, 091, 092, 105, 106, 111 | `chat.push` 전달 대상(묶음 키, 배지, 5회 재시도·10분 유효·DEAD 알림), 기존 알림 배지 변경(`fcm_service`) |
| 4-7 | 실시간 | 015, 016, 017, 028, 029 | 041~044, 046~050, 078, 084~086, 110 | WebSocket 엔드포인트, hub, `chat.realtime` 전달 대상(재시도 없음·SKIPPED), 이벤트 4종, 토큰 만료 종료, nginx 설정 |
| 4-8 | 중복·동시성 | 023~027 | 068, 070~077, 095~097, 099 | 요청 행 잠금(기존 상태 변경 서비스), 동시 요청 테스트 |
| 4-9 | 관리자 조회·기존 지원 채팅방 생성 | 002, 023 | 007, 069 | 관리자 채팅 API, 기존 지원 채팅방 데이터 마이그레이션 |

### 묶음 진행

- [x] 4-1 채팅방 생성·첫 인사·접근 권한 (2026-11-17): `chat_rooms`·`chat_messages`(0035), `OfferCreate.greeting`, `ChatLifecycle.on_offer_created`, `GET /v1/chat-room/{id}`, `GET /v1/chat-room/{id}/messages`, `CHAT_ROOM_NOT_FOUND`. 지원 테스트 요청 본문에 첫 인사 추가
- [x] 4-2 Transactional Outbox (2026-11-17): `outbox_events`·`event_deliveries`(0036), 기록·발행(`SKIP LOCKED`, 발행 재시도)·전달 처리(임대·재시도·SKIPPED·DEAD)·지연/DEAD 알림·관리자 재처리 API·정리 배치, 앱 스케줄러 등록(`OUTBOX_WORKER_ENABLED`, 테스트는 끔). 아직 등록된 전달 대상은 없다(채팅 전달 대상은 4-6·4-7)
- [x] 4-3 채팅 전송·조회·목록 (2026-11-17): `POST /v1/chat-room/{id}/messages`(전송 ID 중복 방지, 채팅방 행 잠금 순번, 보낸 사람 읽음 위치, `chat.message.created` 기록), `GET …/messages`의 `beforeSeq`·`afterSeq`, `GET /v1/chat-room`(커서 페이지, 안읽음 수, 차단 여부 `NONE`), 시스템 채팅 사건 14종과 문구 표(4-4에서 사용), 지원 등록 안내·첫 인사도 이벤트 기록, `CHAT_MESSAGE_ID_CONFLICT`·`CHAT_ROOM_NOT_SENDABLE`
- [x] 4-4 채팅방 상태와 시스템 채팅 (2026-11-17): `room_status.next_room_state`(상태 전이 표, `CLOSED` 불변), `system_chat_delivery`(안읽음·푸시 대상, 분쟁 접수는 접수한 쪽만 푸시), `ChatLifecycle`에 매칭·지원 취소·요청 취소·관리자 취소·신고 승인·임무 완료·분쟁 접수/판정·수행비 입금·환불 완료 추가(채팅방 행 잠금, `system_event_key`로 사건당 1건), 설계 문서 호출 지점 표의 서비스 11곳에 같은 트랜잭션으로 연결. 채팅방이 없는 기존 지원은 건너뛴다(백필은 4-9)
- [x] 4-5 읽음과 안읽음 (2026-11-17): `POST /v1/chat-room/{id}/read`(조건부 UPDATE로 뒤로만, 바뀔 때만 `version` 증가, 없는 순번 `CHAT_READ_SEQ_INVALID`), `GET /v1/chat-room/unread-count`(채팅방별·합계, 닫힌 방 포함), `POST /v1/chat-room/read-all`(요청 시점 위치까지, 더 읽은 방 유지), 상세 응답에 `version`. `chat.read.updated` 기록은 실시간과 함께 4-7에서
- [x] 4-6 채팅 푸시 (2026-11-17): `chat.push` 전달 대상(`ChatPushConsumer`, 5초·30초·1분·2분·4분 5회, 유효 10분), 받는 사람은 일반 채팅의 상대·시스템 채팅 표의 푸시 대상(알림 꺼짐·토큰 없음·탈퇴 제외, 없으면 `SKIPPED`), 묶음 키 `chat-room-{id}`, 배지 = 채팅 안읽음 합계 + 알림 미읽음(`notification/badge.py`, 기존 알림 푸시도 같은 값), 앱 시작 때 등록. Outbox 처리 작업이 같은 대상의 연속 이벤트를 다음 주기로 미루지 않도록 전달 처리를 반복하게 변경(OUTBOX-TS-023)
- [x] 4-7 실시간 (2026-11-17): `GET /v1/chat/ws`(Bearer 인증, 만료·없는 토큰 4401 거부, 연결 중 만료 시 4401 종료, 30초 ping), `app/realtime/hub.py`(사용자별 연결, 다른 스레드에서 전송), `chat.realtime` 전달 대상(재시도 없음, 연결 없음·전송 오류 `SKIPPED`), `chat.room.updated`(`ChatLifecycle`)·`chat.read.updated`(읽음·전체 읽음·전송) 기록과 `version`, nginx `/v1/chat/ws` location(3600s)
- [x] 4-8 중복·동시성 (2026-11-17): `app/services/locking.py`(요청 → 지원 → 임무 순서 잠금, 잠근 행은 최신 값으로 다시 읽음)를 상태를 바꾸는 서비스 진입부에 적용. 동시 요청 테스트 도우미(요청마다 새 세션, 검사 직후 두 요청을 만나게 함). TS-099(채팅방 생성 작업 중 새 지원)는 생성 작업과 함께 4-9로 옮김
- [ ] 4-9

채팅 시나리오 105개(CHAT-TS-102~104, 107~109는 OUTBOX로 옮겨 비움)와 Outbox 시나리오 21개는 위 표에서 한 묶음에만 배정했다.

## 결정 사항

- 실시간은 WebSocket(받기 전용), 전송은 REST, 연결 인증은 `Authorization` 헤더, 프로세스 간 전달은 프로세스 메모리 hub로 한다 (2026-11-17, 설계 문서 "결정한 것").
- 실시간 이벤트와 푸시는 MySQL Transactional Outbox로 전달한다. 변경과 이벤트를 한 트랜잭션에 기록하고, 전달 대상(실시간·푸시)별로 처리·재시도·중복 방지한다. Kafka는 지금 구현하지 않고 별도 서버(라즈베리파이)에 둘 예정이라 발행자 인터페이스와 이벤트 봉투만 맞춘다 (2026-11-17).
- 채팅 푸시는 실패하면 최대 5회 재시도한다(5초·30초·1분·2분·4분). 저장 후 10분 지난 푸시는 보내지 않는다. 앞서 "재시도 없음"으로 정했던 것을 Outbox 도입과 함께 바꿨다 (2026-11-17).
- 실패 처리는 공통 정책([`event-delivery.md`](../../product-specs/event-delivery.md))으로 둔다: 발행은 성공할 때까지(최대 10분 간격) 재시도하고 5분 지연 시 알림, 전달은 대상별 정책으로 재시도 후 `DEAD`·`SKIPPED`, `DEAD`는 알림과 관리자 수동 재처리, 정리 배치는 끝난 이벤트만 7일 뒤 삭제 (2026-11-17).
- Outbox 주기 작업은 10초 처리 작업(발행 → 전달·재시도 → 지연 점검)과 매일 04:00 정리 두 개로 단순화했다. 커밋 직후 바로 실행은 유지한다. 발행 지연 5분 알림(OUTBOX-REQ-003)을 유지하려고 지연 점검은 별도 작업 대신 10초 처리 작업의 마지막 단계로 옮겼다 (2026-11-17).
- 다른 도메인은 `EventBus`가 아니라 `ChatLifecycle`을 같은 트랜잭션에서 직접 호출한다. `EventBus`가 핸들러 예외를 삼켜 원자성을 깨기 때문이다.

## 검증 방법

- 묶음마다 `scripts/verify.sh`(static, unit, integration) 통과. CI에서는 PR이 Draft라 정적·단위만 돌므로, 통합 테스트는 로컬 MySQL(`docker-compose.test.yml`)이나 Ready 전환 후 CI로 확인한다.
- 마지막에 채팅 시나리오 문서 상태에서 `구현 전`을 지워 시나리오 연결 검사를 강제한다(차단 후 시나리오는 skip 테스트로 연결).
- staging 머지 후 실제 앱에서 채팅 전송·실시간 수신·푸시를 확인한다.

## 남은 결정·위험

- 채팅 신고 승인 시 조치는 미결정이다([`chat-reporting.md`](../../product-specs/chat-reporting.md)). 이번 구현 범위 밖이다.
- 지원 등록 API에 첫 인사가 필수가 되므로 앱 배포와 순서를 맞춰야 한다(요구사항 문서 "기존 기능 영향").
