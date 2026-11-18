# 알림·채팅 FCM Payload

문구 정본: [알림 정책](../product-specs/notification-policy.md#noti-req-001--지원-전후-전달-정책), [시스템 채팅](../product-specs/chat-requirements.md#chat-req-021--사건별-시스템-채팅).

## 1. 기존 알림 — 지원 전

알림은 `notifications`에 저장한다. `alarm_enabled=false`도 SKIPPED로 저장하며 푸시는 보내지 않는다. 과거 이력과 전체 공지·관리자 커스텀 알림은 유지한다.

모든 data 값은 문자열이다. 자동 알림 data는 `notification_type`, `proposal_id`를 사용한다. 기존 알림 이력의 `offer_id`는 호환을 위해 유지한다.

```json
{"notification_type": "refund_completed", "proposal_id": "10"}
```

| 사건 | notification_type | 클릭 시 |
|---|---|---|
| 입금 확인·게시물 등록 완료 | payment_completed | 해당 요청 상세 |
| 입금 독촉 | payment_reminder | 홈 |
| 24시간 미입금 취소 | proposal_cancelled | 홈 |
| **추가: 지원 전 행님 취소** | **proposal_cancelled_by_user** | **해당 요청 상세** |
| **추가: 지원 전 관리자 취소** | **proposal_cancelled_by_admin** | **해당 요청 상세** |
| **추가: 지원 전 환불 완료** | **refund_completed** | **해당 요청 상세** |

신규 3종을 기존 미입금 취소 타입과 구분하므로 홈과 상세 이동이 섞이지 않는다. API 처리 트랜잭션에 저장하고 커밋 후 이번에 생성한 PENDING ID만 발송한다. 커스텀 알림 직접 발송 경로의 `notification_id`, `related_entity_type`, `related_entity_id`, `data_*` 계약은 변경하지 않는다.

## 2. 시스템 채팅 — 지원 등록 이후

**변경:** 지원·매칭·미선정·임무 완료·분쟁은 기존 notifications를 새로 만들지 않는다. 시스템 채팅과 푸시가 기존 알림의 제목·본문을 그대로 사용한다. 해당 제목은 조회/실시간의 `systemTitle`, 본문은 `content`다. 별도 제목이 없던 시스템 안내는 `systemTitle=null`이며 푸시 제목은 상대 이름이다. 일반 채팅의 제목도 상대 이름이다.

```json
{"type": "CHAT", "roomId": "25", "messageId": "301", "seq": "7"}
```

클릭하면 `roomId`의 채팅방으로 이동한다. 종료된 방도 기록 조회가 가능하다. 앱은 안내 말풍선 자체를 눌러 별도 화면으로 이동할 필요가 없다. `messageId`는 중복 제거, `seq`는 해당 안내 위치 식별에 사용할 수 있다.

배지는 기존 알림 미읽음 + 채팅 안읽음 합계다. 같은 사건을 두 저장소에 중복 생성하지 않는다. 서버는 연결 여부와 무관하게 푸시하고, 현재 방에서 숨기기/다른 화면 배너/백그라운드 OS 표시는 앱에서 처리한다.

요청 만료 안내와 자동 처리는 TD-021로 보류하며, 완료 리마인드도 기존 미구현 상태다. 실제 모바일 클릭 화면은 앱 연동 검증 대상이다.
