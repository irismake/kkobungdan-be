# Notification FCM Payload

이 문서는 클라이언트가 푸시 알림 수신/클릭 처리에 사용할 FCM payload 계약을 정리한다.

## 공통 규칙

- 모든 자동 알림은 수신자의 `alarm_enabled=true`일 때만 생성된다.
- FCM `notification.title`, `notification.body`에는 아래 표의 타이틀/내용이 들어간다.
- FCM `data`의 모든 값은 문자열이다.
- 발송자 사용자 ID는 현재 payload에 포함하지 않는다. 아래 표의 발송자는 알림을 발생시킨 역할/행위자를 뜻한다.
- 클라이언트 라우팅 code로는 `data.notification_type` 값을 사용한다.
- 자동 알림 payload는 `notification_type`, `offer_id`, `proposal_id`만 전달한다.

## 공통 data 형태

```json
{
  "notification_type": "offer_accepted",
  "offer_id": "45",
  "proposal_id": "10"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `notification_type` | string | 클라이언트 라우팅 code |
| `offer_id` | string | Offer ID |
| `proposal_id` | string | Proposal ID |

## 이벤트별 알림 계약

| 이벤트 | 수신자 | 발송자/원인 | 트리거 | title | body |
|---|---|---|---|---|---|
| 꼬붕 발생 | 행님 | 꼬붕 | `POST /v1/offer` | `누군가 지원했어요! 👀` | `회원님의 요청에 새로운 꼬붕이 생겼어요. 확인해보세요!` |
| 지원 완료 | 꼬붕 | 꼬붕 본인 | `POST /v1/offer` | `지원 완료! ✅` | `지원이 정상적으로 접수됐어요. 행님의 선택을 기다려주세요.` |
| 지원 수락 | 선택된 꼬붕 | 행님 | `POST /v1/offer/{offerId}/accept` | `선택받으셨어요! 🙌` | `행님이 회원님을 선택했어요.` |
| 탈락 통보 | 탈락 꼬붕 전원 | 행님 | `POST /v1/offer/{offerId}/accept` | `이번엔 아쉽게 됐어요 😢` | `이번엔 선택받지 못했지만 다음 기회가 분명 있을 거예요. 다시 도전해보세요!` |
| 꼬붕만 만남 확인 | 행님 | 꼬붕 | `POST /v1/offer/{offerId}/complete-delivery` | `꼬붕이 만남을 확인했어요! 🤝` | `꼬붕이 만남을 확인했어요. 회원님도 확인해주시면 수행비가 꼬붕에게 전달돼요.` |
| 행님만 만남 확인 | 꼬붕 | 행님 | `POST /v1/proposal/{proposalId}/confirm-received` | `행님이 만남을 확인했어요! 🤝` | `행님이 만남을 확인했어요. 회원님도 앱에서 만남을 확인해주시면 정산이 바로 진행돼요!` |
| 양측 확인 완료 (행님) | 행님 | 두 번째 완료 클릭 사용자 | `POST /v1/offer/{offerId}/complete-delivery` 또는 `POST /v1/proposal/{proposalId}/confirm-received` | `미션 수행 완료! 수고하셨어요 🎊` | `양측 만남이 모두 확인됐어요. 성공적으로 미션 수행이 완료됐습니다!` |
| 양측 확인 완료 (꼬붕) | 꼬붕 | 두 번째 완료 클릭 사용자 | `POST /v1/offer/{offerId}/complete-delivery` 또는 `POST /v1/proposal/{proposalId}/confirm-received` | `미션 수행 완료! 수고하셨어요 🎊` | `양측 만남이 모두 확인됐어요. 성공적으로 미션이 완료됐습니다!` |

양측 확인 완료는 두 번째 완료 클릭으로 `ALL_COMPLETED`가 되는 경우에만 발송된다. 타이틀은 동일하고 본문만 수신자별로 다르다. 이때 마지막 클릭에 대한 `meeting_confirmed`는 별도로 발송되지 않는다.
| 행님이 분쟁 접수 | 꼬붕 | 행님 | `POST /v1/proposal/{proposalId}/dispute` | `분쟁이 접수되었어요 🚨` | `행님이 분쟁을 접수했어요. 앱에서 내용을 확인해주세요.` |
| 꼬붕이 분쟁 접수 | 행님 | 꼬붕 | `POST /v1/offer/{offerId}/dispute` | `분쟁이 접수되었어요 🚨` | `꼬붕이 분쟁을 접수했어요. 앱에서 내용을 확인해주세요.` |

## 이벤트별 data payload

### 꼬붕 발생

```json
{
  "notification_type": "offer_new",
  "offer_id": "{offerId}",
  "proposal_id": "{proposalId}"
}
```

### 지원 완료

```json
{
  "notification_type": "offer_submitted",
  "offer_id": "{offerId}",
  "proposal_id": "{proposalId}"
}
```

### 지원 수락

```json
{
  "notification_type": "offer_accepted",
  "offer_id": "{acceptedOfferId}",
  "proposal_id": "{proposalId}"
}
```

### 탈락 통보

```json
{
  "notification_type": "offer_rejected",
  "offer_id": "{acceptedOfferId}",
  "proposal_id": "{proposalId}"
}
```

### 꼬붕만 만남 확인

```json
{
  "notification_type": "meeting_confirmed",
  "offer_id": "{offerId}",
  "proposal_id": "{proposalId}"
}
```

### 행님만 만남 확인

```json
{
  "notification_type": "meeting_confirmed",
  "offer_id": "{offerId}",
  "proposal_id": "{proposalId}"
}
```

### 양측 확인 완료

```json
{
  "notification_type": "execution_completed",
  "offer_id": "{offerId}",
  "proposal_id": "{proposalId}"
}
```

### 행님이 분쟁 접수

```json
{
  "notification_type": "dispute_raised",
  "offer_id": "{offerId}",
  "proposal_id": "{proposalId}"
}
```

### 꼬붕이 분쟁 접수

```json
{
  "notification_type": "dispute_raised",
  "offer_id": "{offerId}",
  "proposal_id": "{proposalId}"
}
```

## 클릭 라우팅 기준

현재 백엔드는 명시적인 `deep_link`나 `target_page`를 내려주지 않는다. 클라이언트는 다음 값을 조합해 이동 대상을 결정한다.

- 1차 기준: `notification_type`
- 상세 조회 ID: `offer_id`
- 필요 시 상위 게시물 ID: `proposal_id`

동일한 `notification_type=meeting_confirmed`는 꼬붕 확인과 행님 확인 모두에서 사용된다. 수신자 역할에 따라 화면 분기가 필요하면 클라이언트의 현재 사용자 역할 또는 Offer/Proposal 상세 조회 결과로 분기한다.

## 구현 주의사항

- `POST /v1/proposal/{proposalId}/confirm-received`에서 생성되는 알림도 즉시 발송 background task에 연결된다. background task에는 해당 이벤트에서 생성된 `PENDING` 알림 id만 전달된다.
- 커스텀 알림 API 경로는 자동 알림과 달리 `notification_id`, `related_entity_type`, `related_entity_id`, `data_*` 필드를 포함할 수 있다. 이 문서는 자동 알림 outbox 발송 payload만 다룬다.
