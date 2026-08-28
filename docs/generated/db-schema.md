# 생성 DB 스키마 스냅샷

## 목적

이 문서는 목표 영속성 스키마의 파생 스냅샷이다.
정본 결정은 [`docs/design-docs/persistence-schema-canonicalization.md`](../design-docs/persistence-schema-canonicalization.md)를 따른다.

현재 코드와 다른 항목은 구현 완료 상태가 아니라 목표 정본 또는 legacy 기준으로 기록한다.

상태·구분 컬럼은 MySQL native `ENUM`을 쓰지 않는다(`CLAUDE.md`). 대신 `VARCHAR` + 이름 붙인
`CHECK` 제약으로 허용값을 고정한다. 모델에서는 `app/models/enum_type.py`의 `enum_column()`이
만드는 non-native Enum 매핑을 쓰고, DB에는 문자열이 저장되고 애플리케이션에는 Python Enum이
돌아온다. 값 검증은 DB(`CHECK`)와 애플리케이션(Pydantic) 양쪽에서 한다.

`CHECK` 제약 이름 규약은 `ck_<table>_<column>_values`다. **상태값을 추가·제거·변경할 때는 해당
제약을 갱신하는 Alembic 마이그레이션을 반드시 함께 작성해야 한다.** 모델만 바꾸면 DB 제약이
옛 목록에 머물러 새 값이 거부된다.

native ENUM으로 남아 있던 6개 컬럼은 `0029_replace_mysql_enums_with_varchar`가 VARCHAR로
전환했고, 열거형 컬럼 11개의 `CHECK` 제약은 `0030_enum_check_constraints`가 걸었다.

## 전체 테이블

| 테이블 | 담당 도메인 | ORM 매핑 | 세부 문서 | 설명 |
|--------|-------------|----------|-----------|------|
| `users` | user/auth | O | `docs/domains/user-auth/README.md` | 사용자 계정 |
| `auth_phone_verifications` | auth | O | `docs/domains/user-auth/README.md` | 회원가입/로그인 전화번호 인증 |
| `phone_verifications` | user legacy | X | 이 문서 | 구 전화번호 인증 테이블. 현재 코드 미사용 |
| `user_fcm_tokens` | user | O | `docs/domains/user-auth/README.md` | 사용자별 FCM 토큰 |
| `user_withdrawal_reason_questions` | user | O | `docs/domains/user-auth/withdrawal-policy.md` | 회원 탈퇴 사유 마스터 |
| `user_withdrawals` | user | O | `docs/domains/user-auth/withdrawal-policy.md` | 회원 탈퇴 사유 선택 이력 |
| `terms_agreements` | terms | O | `docs/exec-plans/completed/terms-agreement/model.md` | 사용자별 필수 약관 동의 |
| `proposals` | bidding/proposal | O | `docs/exec-plans/completed/proposal/model.md` | 심부름 모집 공고 |
| `offers` | bidding/offer | O | `docs/domains/offer/README.md` | 러너 지원서 |
| `missions` | mission | O | `docs/product-specs/mission.md` | 수락된 지원의 수행 단위. 관리자 웹 전용 |
| `refunds` | refund | O | `docs/design-docs/refund-lifecycle.md` | 입금 확인된 요청의 환불 처리 정본 |
| `dispute_evidences` | execution/dispute-evidence | O | `docs/domain.md` | 분쟁 사유 증빙 |
| `dispute_survey_questions` | dispute-survey | O | `docs/api-spec/README.md` | 분쟁 접수 전 설문 질문 마스터 |
| `proposal_report_reason_questions` | proposal-report | O | `docs/product-specs/proposal-reporting.md` | 게시글 신고 사유 마스터 |
| `proposal_reports` | proposal-report | O | `docs/product-specs/proposal-reporting.md` | 사용자 게시글 신고 및 관리자 검토 이력 |
| `payments` | settlement | 목표 O / 현재 미구현 | 이 문서 | 결제/정산 처리 |
| `settlement_accounts` | settlement | O | 이 문서 | 러너 정산 계좌 |

## 관계 요약

```text
users 1 -> N proposals(orderer_id)
users 1 -> N offers(runner_id)
users 1 -> 1 user_fcm_tokens
users 1 -> N user_withdrawals
users 1 -> 1 terms_agreements
users 1 -> 1 settlement_accounts

proposals 1 -> N offers
proposals 1 -> N dispute_evidences
proposals 1 -> N proposal_reports
proposals 1 -> 1 missions
proposals 1 -> 1 refunds
offers 1 -> N dispute_evidences
offers 1 -> 1 missions
missions 1 -> N dispute_evidences
missions 1 -> 0..1 refunds
offers 1 -> 1 payments
```

대부분은 애플리케이션 레벨 관계다. `dispute_evidences.mission_id`만 분쟁이 반드시 미션에 연결된다는
불변식을 DB에서도 보장하기 위해 실제 MySQL FK constraint를 둔다.

## 공통 컬럼 규칙

| 컬럼 | 타입 | Null | 설명 |
|------|------|------|------|
| `created_at` | `datetime(6)` | NO | 생성 시각 |
| `updated_at` | `datetime(6)` | NO | 수정 시각 |

예외 없이 모든 현재 ORM 대상 테이블은 위 감사 컬럼을 가진다.
Legacy `phone_verifications`도 migration 기준으로 감사 컬럼이 있다.

## `users`

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `varchar(36)` | NO | PK | 사용자 UUID |
| `password_hash` | `varchar(255)` | YES |  | 비밀번호 해시. 현재 phone-auth 흐름에서는 null 가능 |
| `name` | `varchar(100)` | YES |  | 사용자 이름 |
| `phone` | `varchar(20)` | YES | UNIQUE `uk_users_phone` | 정규화된 전화번호 |
| `phone_verified_at` | `datetime(6)` | YES |  | 전화번호 인증 완료 시각 |
| `last_login_at` | `datetime(6)` | YES |  | 마지막 로그인 시각 |
| `alarm_enabled` | `boolean` | YES |  | 알림 수신 동의 여부 |
| `level` | `integer` | NO |  | 성공 완료한 러너 Offer 수 기반 레벨 |
| `is_admin` | `boolean` | NO |  | 관리자 웹 전용 계정 여부. 앱 사용자는 항상 거짓 |
| `admin_username` | `varchar(50)` | YES | UNIQUE `uk_users_admin_username` | 관리자 로그인 아이디. 관리자 행에만 값이 있다 |
| `admin_login_failed_count` | `int` | NO |  | 관리자 로그인 연속 실패 횟수. 성공하면 0으로 되돌린다 |
| `admin_locked_until` | `datetime` | YES |  | 관리자 로그인 잠금 해제 시각. 연속 실패 5회에서 10분 뒤로 설정된다 |
| `deleted` | `boolean` | NO | INDEX `idx_users_deleted` | 탈퇴 여부 |
| `deleted_at` | `datetime(6)` | YES |  | 탈퇴 처리 시각 |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

메모:

- `id`는 애플리케이션에서 UUID로 생성한다.
- `phone`은 하이픈/공백 제거 및 `+82` -> `0` 변환 후 저장한다.
- 탈퇴 시 `deleted = true`로 표시한다. 이 값은 회원 탈퇴 정책의 `WITHDRAWN` 상태에 해당한다.
- 탈퇴 시 개인정보 필드는 `null`로 영구 삭제한다. 활동 조회에서만 작성자를 `탈퇴한 사용자`로 표시한다.
- 관리자 계정은 휴대폰이 없어 SMS 로그인 경로로는 토큰을 받을 수 없다. `POST /v1/admin/auth/login`만 사용한다.
  계정은 앱 기동 시 `ADMIN_USERNAME` / `ADMIN_INITIAL_PASSWORD` 설정값으로 한 번만 만든다.
- 탈퇴 후 `phone = null`이 되므로 동일 전화번호로 새 사용자 가입이 가능하며, 기존 활동 이력은 새 User ID와 연결하지 않는다.

## `auth_phone_verifications`

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | 인증 요청 ID |
| `purpose` | `varchar(10)` | NO | `idx_auth_phone_verifications_purpose_phone_status_expires`, `idx_auth_phone_verifications_purpose_phone_status` | `SIGNUP`, `LOGIN` |
| `phone` | `varchar(20)` | NO | 같은 복합 인덱스 | 정규화된 전화번호 |
| `name` | `varchar(100)` | YES |  | 회원가입 요청 이름 |
| `carrier` | `varchar(50)` | YES |  | 통신사 |
| `code_hash` | `varchar(100)` | NO |  | 인증 코드 해시 |
| `status` | `varchar(20)` | NO | 같은 복합 인덱스 | `PENDING`, `VERIFIED`, `EXPIRED` |
| `expires_at` | `datetime(6)` | NO | 같은 복합 인덱스 | 만료 시각 |
| `sent_at` | `datetime(6)` | NO |  | 발송 시각 |
| `verified_at` | `datetime(6)` | YES |  | 인증 완료 시각 |
| `attempt_count` | `integer` | NO |  | 코드 확인 실패 횟수 |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

현재 코드 메모:

- SQLAlchemy 인덱스명은 `idx_auth_phone_verifications_purpose_phone_status_expires_at`로 선언되어 있다.
- `created_at`, `updated_at`은 DB default 없이 ORM에서 insert/update 시 채운다.

## `phone_verifications`

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | 인증 요청 ID |
| `user_id` | `varchar(36)` | NO | `idx_phone_verifications_user_status_expires` | 사용자 ID |
| `phone` | `varchar(20)` | NO | `idx_phone_verifications_phone_status` | 인증 대상 전화번호 |
| `code_hash` | `varchar(100)` | NO |  | 인증 코드 해시 |
| `status` | `varchar(20)` | NO | 복합 인덱스 | 인증 상태 |
| `expires_at` | `datetime(6)` | NO | 복합 인덱스 | 만료 시각 |
| `sent_at` | `datetime(6)` | NO |  | 발송 시각 |
| `verified_at` | `datetime(6)` | YES |  | 인증 완료 시각 |
| `attempt_count` | `integer` | NO |  | 코드 확인 실패 횟수 |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

메모:

- Legacy 전화번호 인증 테이블이다.
- 현재 ORM 모델과 repository가 없으며, 신규 인증 흐름은 `auth_phone_verifications`를 사용한다.

## `user_fcm_tokens`

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | 토큰 row ID |
| `user_id` | `varchar(36)` | NO | UNIQUE `uk_user_fcm_tokens_user_id` | 사용자 ID |
| `fcm_token` | `varchar(4096)` | NO |  | FCM 등록 토큰 |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

## `user_withdrawal_reason_questions`

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | 탈퇴 사유 ID |
| `question_text` | `varchar(500)` | NO |  | 탈퇴 사유 문구 |
| `display_order` | `integer` | NO | UNIQUE `uk_user_withdrawal_reason_questions_display_order`, INDEX `idx_user_withdrawal_reason_questions_lookup` | 표시 순서 |
| `is_active` | `boolean` | NO | INDEX `idx_user_withdrawal_reason_questions_lookup` | 조회 노출 여부 |
| `requires_detail` | `boolean` | NO |  | 상세 사유 필수 여부 |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

## `user_withdrawals`

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | 탈퇴 이력 ID |
| `user_id` | `varchar(36)` | NO | INDEX `ix_user_withdrawals_user_id`, INDEX `idx_user_withdrawals_user_withdrawn_at` | 탈퇴 사용자 ID |
| `reason_question_id` | `bigint` | YES | INDEX `idx_user_withdrawals_reason_question_id` | 선택한 탈퇴 사유 ID |
| `detail_reason` | `varchar(500)` | YES |  | 선택 상세 사유 |
| `withdrawn_at` | `datetime(6)` | NO | INDEX `ix_user_withdrawals_withdrawn_at`, INDEX `idx_user_withdrawals_user_withdrawn_at` | 탈퇴 처리 시각 |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

## `terms_agreements`

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | 약관 동의 row ID |
| `user_id` | `varchar(36)` | NO | UNIQUE `uk_terms_agreements_user_id`, INDEX `idx_terms_agreements_user_id` | 사용자 ID |
| `terms_of_service` | `boolean` | NO |  | 이용약관 동의 |
| `privacy_policy` | `boolean` | NO |  | 개인정보처리방침 동의 |
| `payment_refund_policy` | `boolean` | NO |  | 결제/환불지급정책 동의 |
| `agreed_at` | `datetime(6)` | NO |  | 동의 시각 |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

## `proposals`

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | 공고 ID |
| `orderer_id` | `varchar(36)` | NO | INDEX `idx_proposals_orderer_id` | 요청 작성자 사용자 ID |
| `title` | `varchar(50)` | NO |  | 공고 제목 |
| `content` | `varchar(500)` | NO |  | 요청 상세 내용 |
| `deadline` | `datetime(6)` | NO |  | UTC 기준 수행 마감 시각 |
| `meeting_at` | `datetime(6)` | NO |  | legacy 호환 컬럼. 현재 API 미노출 |
| `errand_fee` | `integer` | NO |  | 심부름비 |
| `item_price` | `integer` | NO |  | legacy 호환 컬럼. 현재 API 미노출 |
| `deposit` | `integer` | NO |  | legacy 호환 컬럼. 현재 API 미노출 |
| `status` | `varchar(20)` | NO |  | `HOLDING`, `POSTED`, `OFFERED`, `MATCHED`, `ORDER_COMPLETED`, `ALL_COMPLETED`, `DISPUTED`, `REFUND_PENDING`, `REFUNDED`, `REPORTED`, `CANCELLED` |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `matched_at` | `datetime(6)` | YES |  | Offer 수락으로 매칭된 시각 |
| `runner_confirmed_at` | `datetime(6)` | YES |  | 러너 완료 확인 시각 |
| `orderer_confirmed_at` | `datetime(6)` | YES |  | 오더러 완료 확인 시각 |
| `settled_at` | `datetime(6)` | YES |  | legacy 호환 컬럼. 현재 API 미노출 |
| `disputed_at` | `datetime(6)` | YES |  | 분쟁 접수 시각 |
| `resolved_at` | `datetime(6)` | YES |  | 분쟁 해결 시각 |
| `open_chat_url` | `varchar(500)` | YES |  | 입금 확인 시 관리자가 입력한 오픈채팅방 URL |
| `admin_note` | `varchar(500)` | YES |  | 관리자 취소 메모 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

## `offers`

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | Offer ID |
| `proposal_id` | `bigint` | NO | UNIQUE `uk_proposal_runner` 일부 | 대상 Proposal ID |
| `runner_id` | `varchar(36)` | NO | UNIQUE `uk_proposal_runner` 일부, INDEX `idx_offers_runner_id` | 지원자 사용자 ID |
| `status` | `varchar(20)` | NO |  | `WAITING`, `ACCEPTED`, `RUNNER_COMPLETED`, `ALL_COMPLETED`, `DISPUTED`, `REJECTED`, `CANCELLED` |
| `open_chat_url` | `varchar(500)` | YES |  | 미사용. 링크는 `proposals.open_chat_url`이 정본이다 |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `accepted_at` | `datetime(6)` | YES |  | 오더가 Offer를 수락한 시각 |
| `runner_confirmed_at` | `datetime(6)` | YES |  | 러너 완료 확인 시각 |
| `orderer_confirmed_at` | `datetime(6)` | YES |  | 오더러 완료 확인 시각 |
| `settled_at` | `datetime(6)` | YES |  | legacy 호환 컬럼. 현재 API 미노출 |
| `disputed_at` | `datetime(6)` | YES |  | 분쟁 접수 시각 |
| `resolved_at` | `datetime(6)` | YES |  | 분쟁 해결 시각 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

## `missions`

수락된 지원 하나에 대응하는 수행 단위. 앱에는 노출하지 않고 관리자 웹에서만 사용한다.
상태는 `proposals`와 `offers`의 상태에서 파생하되 상태별 목록 조회를 위해 컬럼으로 실체화한다.

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | 미션 ID |
| `proposal_id` | `bigint` | NO | UNIQUE `uk_missions_proposal_id` | 대상 Proposal ID |
| `offer_id` | `bigint` | NO | UNIQUE `uk_missions_offer_id` | 수락된 Offer ID |
| `orderer_id` | `varchar(36)` | NO | INDEX `idx_missions_orderer_id` | 행님 사용자 ID |
| `runner_id` | `varchar(36)` | NO | INDEX `idx_missions_runner_id` | 꼬붕 사용자 ID |
| `status` | `varchar(20)` | NO | INDEX `idx_missions_status` | `STARTED`, `DISPUTED`, `COMPLETED`, `PAID`, `FAILED` |
| `errand_fee` | `int` | NO |  | 수행비. 지급액과 환불액의 근거 금액 |
| `started_at` | `datetime(6)` | NO |  | 미션 시작 시각. Offer 수락 시각 |
| `disputed_at` | `datetime(6)` | YES |  | 분쟁 전환 시각 |
| `completed_at` | `datetime(6)` | YES |  | 미션 완료 시각 |
| `failed_at` | `datetime(6)` | YES |  | 미션 실패 시각 |
| `resolution` | `varchar(20)` | YES |  | 관리자 분쟁 판정 결과. `COMPLETED` 또는 `FAILED` |
| `resolved_at` | `datetime(6)` | YES |  | 분쟁 판정 시각 |
| `resolved_by_admin_id` | `varchar(36)` | YES |  | 판정한 관리자 ID |
| `settlement_paid_at` | `datetime(6)` | YES |  | 꼬붕 수행비 입금 시각. null이면 미지급 |
| `settlement_paid_by_admin_id` | `varchar(36)` | YES |  | 지급 처리 관리자 ID |
| `settlement_rejected_at` | `datetime(6)` | YES |  | 수행비 지급 반려 시각 |
| `settlement_rejected_by_admin_id` | `varchar(36)` | YES |  | 지급 반려 관리자 ID |
| `payout_memo` | `varchar(200)` | YES |  | 이체 참조번호 등 관리자 메모 |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

지급 여부는 별도 boolean 없이 `settlement_paid_at`의 null 여부로 판정한다.
관리자 웹의 수행비 지급(payout)은 이 컬럼에서 파생한다. 환불 정본은 `refunds`이며 Mission은
환불 처리와 무관하게 수행 결과인 `FAILED`를 유지한다. 지급 반려는 기록만 남기고 미션 상태를
되돌리지 않는다.

꼬붕·행님의 완료 확인 시각은 `missions`에 복제하지 않는다. 정본은 `offers.runner_confirmed_at`과
`offers.orderer_confirmed_at`이며, 관리자 미션 응답에서 조회 시점에 합쳐 내려준다.

현재 코드 갭:

- 없음.

## `refunds`

입금 확인 후 취소된 Proposal의 전액 환불 처리 정본이다. 매칭 전 취소는 `mission_id`가 없고,
수락 이후 분쟁 또는 관리자 취소는 Mission도 함께 참조한다.

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | 관리자 환불 API의 refund ID |
| `proposal_id` | `bigint` | NO | UNIQUE `uk_refunds_proposal_id` | 환불 대상 Proposal ID |
| `mission_id` | `bigint` | YES | UNIQUE `uk_refunds_mission_id` | 수락 이후 환불이면 연결된 Mission ID |
| `orderer_id` | `varchar(36)` | NO | INDEX `ix_refunds_orderer_id` | 환불받을 행님 사용자 ID |
| `amount` | `integer` | NO |  | 요청의 수행비 전액 |
| `reason` | `varchar(30)` | NO |  | `USER_CANCELLED`, `ADMIN_CANCELLED`, `DISPUTE_FAILED`, `PAYMENT_EXPIRED` |
| `reason_detail` | `text` | YES |  | 관리자 취소 메모 또는 사용자 분쟁 사유 |
| `status` | `varchar(20)` | NO | INDEX `idx_refunds_status_requested` | `REVIEW`, `PENDING`, `COMPLETED`, `VOIDED` |
| `requested_at` | `datetime(6)` | NO | INDEX `idx_refunds_status_requested` | 환불 대상 확정 시각 |
| `processed_at` | `datetime(6)` | YES |  | 환불 완료 시각 |
| `processed_by_admin_id` | `varchar(36)` | YES |  | 처리 관리자 ID |
| `admin_note` | `varchar(200)` | YES |  | 이체 참조번호 등 처리 메모 |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

## `dispute_evidences`

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | 분쟁 증빙 ID |
| `proposal_id` | `bigint` | NO | INDEX `ix_dispute_evidences_proposal_id` | 연관 Proposal ID |
| `offer_id` | `bigint` | NO | INDEX `ix_dispute_evidences_offer_id` | 연관 Offer ID |
| `mission_id` | `bigint` | NO | FK `fk_dispute_evidences_mission_id`, INDEX `idx_dispute_evidences_mission_id` | 연관 Mission ID |
| `actor_id` | `varchar(36)` | NO | INDEX `ix_dispute_evidences_actor_id` | 분쟁 접수 사용자 ID |
| `reason` | `text` | YES |  | 분쟁 상세 사유. 기타 사유에서만 필수라 nullable |
| `survey_question_id` | `bigint` | NO | INDEX `idx_dispute_evidences_survey_question_id` | 선택한 분쟁 설문 질문 ID |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `status` | `varchar(20)` | NO | INDEX `idx_dispute_evidences_status` | 관리자 처리 상태. `PENDING`, `RESOLVED` |
| `admin_note` | `varchar(500)` | YES |  | 관리자 처리 메모 |
| `resolved_at` | `datetime(6)` | YES |  | 관리자 처리 시각 |
| `resolved_by_admin_id` | `varchar(36)` | YES |  | 처리한 관리자 ID |

`status`는 요청·지원의 진행 상태와 다른 축이다. 접수 건을 관리자가 처리했는지만 나타낸다.

`0025_link_disputes_to_missions` 마이그레이션은 기존 행을 `offer_id`로 백필하고, 연결되지 않은 행이
남아 있으면 NOT NULL 전환 전에 중단한다. staging에서 중단되면 해당 분쟁의 Offer/Mission 관계를
먼저 복구해야 한다.

## `dispute_survey_questions`

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | 질문 ID |
| `target_type` | `varchar(10)` | NO | UNIQUE `uk_dispute_survey_questions_target_order` 일부, INDEX `idx_dispute_survey_questions_lookup` | `ORDER`, `RUNNER` |
| `question_text` | `varchar(500)` | NO |  | 질문 내용 |
| `display_order` | `integer` | NO | UNIQUE `uk_dispute_survey_questions_target_order` 일부, INDEX `idx_dispute_survey_questions_lookup` | 클라이언트 표시 순서 |
| `is_active` | `boolean` | NO | INDEX `idx_dispute_survey_questions_lookup` | 조회 노출 여부 |
| `requires_detail` | `boolean` | NO |  | 상세 사유 필수 여부. `기타` 문항만 `true` |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

현재 코드 메모:

- 분쟁 접수 API는 `reasonQuestionId`를 필수로, `detailReason`을 선택으로 받는다. 저장 컬럼은 각각 `survey_question_id`, `reason`이다.
  질문의 `requires_detail`이 `true`(=`기타`)일 때만 `detailReason`이 필수다. 신고·탈퇴와 같은 정책이다.
- `GET /v1/dispute-survey/questions`는 active 질문만 대상별 순서대로 반환한다.
- 문항은 `0028_seed_dispute_survey_questions`가 코드로 넣는다. 신고(`0015`)·탈퇴(`0018`)와 같은 방식이라
  환경별로 직접 `INSERT`할 필요가 없다. 정본은 ORDER 5개·RUNNER 5개이고 `기타`만 `requires_detail = 1`이다.
- 시드는 `target_type`별로 행이 하나도 없을 때만 삽입한다. 문항이 이미 있는 환경은 문구를 건드리지 않고,
  문구가 정본과 완전히 일치하는 행의 `requires_detail`만 정본 값으로 맞춘다.
- 문항을 바꿀 때는 손으로 `INSERT`하지 말고 새 마이그레이션을 쓴다. `requires_detail`을 빠뜨리면 컬럼 기본값
  `0`이 적용돼 목록 응답의 `requiresDetail`이 `false`로 나가고, 클라이언트 가드와 서버 검증이 함께 풀린다.

## `proposal_report_reason_questions`

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | 신고 사유 ID |
| `question_text` | `varchar(500)` | NO |  | 신고 사유 문구 |
| `display_order` | `integer` | NO | UNIQUE `uk_proposal_report_reason_questions_display_order`, INDEX `idx_proposal_report_reason_questions_lookup` | 표시 순서 |
| `is_active` | `boolean` | NO | INDEX `idx_proposal_report_reason_questions_lookup` | 조회 노출 여부 |
| `requires_detail` | `boolean` | NO |  | 상세 사유 필수 여부. `기타` 문항만 `true` |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

## `proposal_reports`

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | 신고 ID |
| `proposal_id` | `bigint` | NO | UNIQUE `uk_proposal_reports_proposal_reporter` 일부, INDEX `idx_proposal_reports_proposal_status` | 신고 대상 Proposal ID |
| `reporter_id` | `varchar(36)` | NO | UNIQUE `uk_proposal_reports_proposal_reporter` 일부, INDEX `idx_proposal_reports_reporter_id` | 신고 사용자 ID |
| `reason_question_id` | `bigint` | NO |  | 선택한 신고 사유 ID |
| `detail_reason` | `varchar(500)` | YES |  | 선택 상세 사유 |
| `status` | `varchar(20)` | NO | INDEX `idx_proposal_reports_proposal_status`, `idx_proposal_reports_status_created` | `PENDING`, `ACCEPTED`, `REJECTED` |
| `created_at` | `datetime(6)` | NO | INDEX `idx_proposal_reports_status_created` | 신고 접수 시각 |
| `reviewed_at` | `datetime(6)` | YES |  | 관리자 검토 시각 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

## `payments`

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | Payment ID |
| `offer_id` | `bigint` | NO | UNIQUE `uk_offer_id` | 정산 대상 Offer ID |
| `orderer_id` | `varchar(36)` | NO | INDEX `idx_payments_orderer_id` | 요청자 사용자 ID 스냅샷 |
| `runner_id` | `varchar(36)` | NO | INDEX `idx_payments_runner_id` | 수행자 사용자 ID 스냅샷 |
| `run_fee` | `decimal(10,2)` | NO |  | 수행 수수료 |
| `item_price` | `decimal(10,2)` | NO |  | 물품 금액 |
| `total_amount` | `decimal(10,2)` | NO |  | 총 결제 금액 |
| `settlement_amount` | `decimal(10,2)` | NO |  | 러너 정산 금액 |
| `pg_transaction_id` | `varchar(100)` | YES |  | PG 거래 ID |
| `pg_response` | `text` | YES |  | PG 응답 원문 |
| `status` | `varchar(20)` | NO |  | `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`, `REFUNDED` |
| `processing_started_at` | `datetime(6)` | YES |  | 결제 처리 시작 시각 |
| `completed_at` | `datetime(6)` | YES |  | 결제 완료 시각 |
| `failed_at` | `datetime(6)` | YES |  | 결제 실패 시각 |
| `refunded_at` | `datetime(6)` | YES |  | 환불 완료 시각 |
| `failure_reason` | `text` | YES |  | 실패 사유 |
| `retry_count` | `integer` | NO |  | 결제 재시도 횟수 |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

현재 코드 메모:

- `payments` ORM 모델은 아직 없다.
- 회원 탈퇴의 미결 환불·수행비 지급은 현재 `missions`의 완료·반려 시각으로 차단한다. 향후 `payments` ORM이 도입되면 결제 처리 중 상태도 추가한다.
- 기존 문서의 `payer_id`, `payee_id`, `amount`, `currency`, `provider`, `external_tx_id` 기준은 이 목표 정본으로 대체한다.

## `settlement_accounts`

| 컬럼 | 타입 | Null | 키/인덱스 | 설명 |
|------|------|------|-----------|------|
| `id` | `bigint` | NO | PK, auto increment | 정산 계좌 row ID |
| `user_id` | `varchar(36)` | NO | UNIQUE `uk_settlement_accounts_user_id`, INDEX `idx_settlement_accounts_user_id` | 계좌 소유 사용자 ID |
| `bank_name` | `varchar(50)` | NO |  | 은행명 |
| `account_holder` | `varchar(100)` | NO |  | 계좌주명 |
| `encrypted_account_number` | `varchar(500)` | NO |  | 암호화된 계좌번호 |
| `masked_account_number` | `varchar(50)` | NO |  | 표시용 마스킹 계좌번호 |
| `created_at` | `datetime(6)` | NO |  | 생성 시각 |
| `updated_at` | `datetime(6)` | NO |  | 수정 시각 |

현재 코드 메모:

- `settlement_accounts` ORM 모델은 `app/models/settlement.py`에 있다.
- 운영 전 `encrypted_account_number` 저장 방식은 KMS 또는 별도 암호화 유틸로 교체해야 한다.

## 목표 정본 외 현재 보조 테이블

아래 테이블은 현재 코드에 있지만 핵심 목표 정본 10개 테이블에는 포함하지 않는다. 별도 알림 문서에서 관리한다.

| 테이블 | 모델 | 설명 |
|--------|------|------|
| `device_tokens` | `app/models/notification.py` | 다중 디바이스 FCM 토큰 |
| `notifications` | `app/models/notification.py` | 알림 발송/상태 로그 |
| `notification_preferences` | `app/models/notification.py` | 사용자 알림 선호 설정 |

## 기준 문서

- [`docs/design-docs/persistence-schema-canonicalization.md`](../design-docs/persistence-schema-canonicalization.md)
- [`docs/domain.md`](../domain.md)
- [`docs/domains/README.md`](../domains/README.md)
