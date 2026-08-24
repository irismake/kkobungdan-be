# 관리자 웹 API 구축

작성일: 2026-08-22 · 상태: 구현 완료 · 근거 문서: `admin-api-contract.md`, `admin-backend-handoff.md`(프론트엔드 전달본)

## 배경

관리자 웹(별도 프론트엔드)이 요청·지원·분쟁·환불·수행비 지급·신고를 처리할 API를 요구한다.
전달받은 핸드오프 문서는 신규 17개 + 기존 4개 수정을 제안하며, 백엔드 결정 12건(BLOCKING 9)을 남겨 두었다.

## 결정 사항

핸드오프 문서의 미확정 항목을 다음과 같이 확정한다.

| # | 항목 | 결정 |
|---|---|---|
| D1 | Mission 도메인 존재 여부 | **이미 존재한다.** `missions` 테이블과 `/v1/admin/missions/*` 4개가 구현되어 있다. FE 문서는 이 커밋 이전에 작성됐다 |
| D2 | 상태 매핑 | 서버는 기존 enum을 그대로 내려주고 한글 라벨 변환은 FE Domain 계층이 맡는다(NON-BLOCKING, 변경 없음) |
| D3 | 관리자 인증 | 후속 작업 `2026-08-22-admin-auth.md`에서 처리했다. 단일 관리자 계정 + 아이디/비밀번호 로그인 |
| D4 | Offer 금액 | Offer에 금액 개념이 **없다.** `AdminOfferSummaryResponse.amount`는 `Proposal.errand_fee`를 내려주고 그렇게 문서화한다 |
| D5 | 입금자명 / 플랫폼 계좌 | 입금자명은 어느 도메인에도 없다 → `depositorName`은 항상 `null`로 내려주고 필드만 확보한다. 플랫폼 입금 계좌는 요청별 데이터가 아니므로 **설정값**(`ADMIN_DEPOSIT_*`)에서 읽는다 |
| D6 | `pending-payment` | **폐기 예정으로 표시**한다. `GET /v1/admin/proposal?status=HOLDING`으로 흡수하고, 기존 경로는 `deprecated`로 두되 응답을 `PageResponse`로 정의하고 `page`/`size`로 정렬한다 |
| D7 | 환불 cardinality | **2026-08-24 변경:** Proposal 1건당 Refund 1건. 매칭 전 유료 취소도 포함한다 |
| D8 | `offer/{id}/resolve` | **이 백엔드에는 존재하지 않는 엔드포인트다**(FE가 참조한 openapi.json이 오래된 사본이다). 분쟁 처리 단위는 Dispute이며 `/v1/admin/dispute/{id}/resolve`가 담당한다 |
| D9 | 신고 승인 cascade | 현재 서버는 승인 시 Proposal을 `REPORTED`로 바꾸고 대기 중 지원을 `REJECTED` 처리한다. **`CANCELLED`로 바꾸지 않는다.** FE 안내 문구를 서버 동작(`REPORTED`)에 맞춰야 한다 |
| D10 | Dispute 처리 상태 | `dispute_evidences`를 **확장**한다(`status`, `admin_note`, `resolved_at`, `resolved_by_admin_id`). 별도 도메인을 만들지 않는다. 신청 대상자는 요청·지원에서 파생한다 |
| D11 | adminNote | 각 도메인 **단일 필드**. 이력 테이블은 만들지 않는다 |
| D12 | 비마스킹 계좌 | 관리자 상세에 한해 복호화한 전체 계좌번호를 내려준다. 목록에는 넣지 않는다 |
| — | Refund / Payout 구조 | Payout은 Mission 투영을 유지한다. Refund는 매칭 전 취소를 포함하기 위해 `refunds` 정본으로 분리했다. 상세 결정은 [`../design-docs/refund-lifecycle.md`](../../design-docs/refund-lifecycle.md)를 따른다 |

### Refund / Payout 처리 상태 매핑

```
PayoutStatus  PENDING   = mission.status == COMPLETED and settlement_paid_at is null and settlement_rejected_at is null
              COMPLETED = mission.status == PAID
              REJECTED  = settlement_rejected_at is not null and settlement_paid_at is null

RefundStatus  PENDING   = refund.status == PENDING
              COMPLETED = refund.status == COMPLETED
```

`refundId`는 **Refund ID**, `payoutId`는 **미션 ID**다. 환불은 확정된 의무라 반려 상태와
반려 엔드포인트를 두지 않는다.

## 스키마 변경

| 테이블 | 변경 |
|---|---|
| `proposals` | `open_chat_url VARCHAR(500) NULL` 추가 — 입금 확인 시 관리자가 입력한 오픈채팅방 URL. 수락된 지원이 생기기 전 단계라 지원에 둘 수 없다 |
| `proposals` | `admin_note VARCHAR(500) NULL` 추가 — 관리자 취소 메모 |
| `dispute_evidences` | `status VARCHAR(20) NOT NULL DEFAULT 'PENDING'`, `admin_note VARCHAR(500) NULL`, `resolved_at DATETIME NULL`, `resolved_by_admin_id VARCHAR(36) NULL` 추가 |
| `missions` | `settlement_rejected_at`, `settlement_rejected_by_admin_id` 추가 — 수행비 지급 반려 기록 |

ENUM 금지 규칙에 따라 전부 `VARCHAR`를 쓴다.

## 엔드포인트

### 수정

- `POST /v1/admin/proposal/{proposal_id}/confirm-payment` — `{ openChatUrl }` 본문 추가(필수, http/https)
- `GET /v1/admin/proposal/pending-payment` — `page`/`size` + `PageResponse`, `deprecated`
- `GET /v1/admin/proposal-reports` — `keyword`, `proposalId` 쿼리 + `proposalStatus` 응답 필드
- `POST /v1/admin/offer/{offer_id}/resolve` — 코드에 없는 엔드포인트라 손대지 않았다. 대체는 dispute resolve

### 신규

```
GET  /v1/admin/summary
GET  /v1/admin/proposal
GET  /v1/admin/proposal/{proposal_id}
POST /v1/admin/proposal/{proposal_id}/cancel
GET  /v1/admin/offer
GET  /v1/admin/dispute
GET  /v1/admin/dispute/{dispute_id}
POST /v1/admin/dispute/{dispute_id}/resolve
POST /v1/admin/dispute/{dispute_id}/reject
GET  /v1/admin/refund
GET  /v1/admin/refund/{refund_id}
POST /v1/admin/refund/{refund_id}/complete
GET  /v1/admin/payout
GET  /v1/admin/payout/{payout_id}
POST /v1/admin/payout/{payout_id}/complete
POST /v1/admin/payout/{payout_id}/reject
```

경로 등록 순서: `/proposal/pending-payment`를 `/proposal/{proposal_id}`보다 먼저 등록한다.

## 파일 계획

| 파일 | 작업 |
|---|---|
| `alembic/versions/0023_admin_web_api_columns.py` | 신규 — 위 4개 테이블 컬럼 |
| `app/models/proposal.py` | `open_chat_url`, `admin_note` + `admin_cancel()` |
| `app/models/dispute_evidence.py` | 처리 상태 컬럼 + `DisputeProcessStatus` |
| `app/models/mission.py` | 지급 반려 컬럼 + `reject_settlement()` |
| `app/schemas/admin.py` | 신규 — 관리자 전용 Request/Response DTO 일체 |
| `app/services/admin/admin_query_service.py` | 신규 — 목록·상세·요약 조회 |
| `app/services/admin/admin_command_service.py` | 신규 — 취소·분쟁·환불·지급 처리 |
| `app/api/v1/admin/admin_router.py` | 신규 라우트 등록 및 기존 4건 수정 |
| `app/core/config.py` | `ADMIN_DEPOSIT_BANK_NAME` / `_ACCOUNT_NUMBER` / `_HOLDER` |
| `app/core/errors.py` | 필요한 신규 에러 코드 |
| `tests/test_admin_integration.py` | 신규 엔드포인트 통합 테스트 |

## 검증 결과 (2026-08-22)

- `pytest` 전체 233건 통과. 신규 `tests/test_admin_web_api_integration.py` 23건 포함
- `alembic upgrade head` → `downgrade 0022` → `upgrade head`를 빈 MySQL에서 왕복 확인.
  베이스라인이 현재 모델 메타데이터로 테이블을 만들기 때문에 0023은 컬럼 존재 여부를 확인한 뒤 추가한다
- `docs/generated/db-schema.md` 갱신 완료

## 기존 계약 변경 (FE 영향)

1. `POST /v1/admin/proposal/{id}/confirm-payment` — `{ "openChatUrl": "https://..." }` 본문이 **필수**가 됐다
2. `GET /v1/admin/proposal/pending-payment` — 응답이 배열에서 `PageResponse`로, 쿼리가 `skip`/`limit`에서 `page`/`size`로 바뀌었고 `deprecated`로 표시했다

## 남은 일

- ~~**D3 관리자 인증**~~ — `2026-08-22-admin-auth.md`에서 완료. `/v1/admin/*`은 관리자 토큰을 요구한다
- `depositorName` 수집 경로 — 값을 만드는 흐름이 없어 항상 `null`이다. 제품 결정이 필요하다
- FE의 신고 승인 안내 문구 — 서버는 승인 시 요청을 `REPORTED`로 바꾼다. `CANCELLED`가 아니다 (D9)
