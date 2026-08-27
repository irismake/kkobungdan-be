# 분쟁·신고·탈퇴 사유 입력 정책 통일

작성일: 2026-08-26 · 상태: 구현 완료 · 근거 문서: [`../../domains/user-auth/withdrawal-policy.md`](../../domains/user-auth/withdrawal-policy.md)

## 배경

같은 "사유 3종"(`reasonQuestionId`, `reasonQuestionText`, `detailReason`) 계약을 쓰면서 입력 규칙이
흐름마다 달랐다. 분쟁은 사유와 상세 사유가 모두 필수였고, 신고는 `기타`를 골라도 상세 사유를
요구하지 않았으며, 탈퇴는 사유 자체가 선택이었다. 클라이언트가 화면마다 다른 검증을 들고 있어야 했다.

## 결정 사항

| # | 항목 | 결정 |
|---|---|---|
| R1 | 사유 선택 | 분쟁·신고·탈퇴 모두 `reasonQuestionId`는 **필수**다. 탈퇴는 선택에서 필수로 올라갔다 |
| R2 | 상세 사유 | `detailReason`은 선택이지만, 고른 사유의 `requires_detail`이 `true`(=`기타`)면 필수다. 없으면 `VALIDATION_ERROR("detailReason")` |
| R3 | 필수 여부의 정본 | 문구 비교(`question_text == "기타"`)가 아니라 탈퇴와 같이 `requires_detail` 컬럼을 정본으로 둔다. `dispute_survey_questions`, `proposal_report_reason_questions`에 컬럼을 추가하고 기존 `기타` 행을 `true`로 백필한다 |
| R4 | 질문 목록 응답 | 탈퇴와 동일하게 `requiresDetail`을 함께 내려준다. 클라이언트가 상세 입력 필수 여부를 문구로 추측하지 않게 한다 |
| R5 | 저장 컬럼 | 사유 ID 컬럼은 NOT NULL을 유지한다. 상세 사유를 담는 `dispute_evidences.reason`만 nullable로 바꾼다 |
| R6 | 응답 계약 | 사유 3종 중 `detailReason`만 nullable이다. 탈퇴 응답의 `reasonQuestionId`·`reasonQuestionText`는 non-null로 좁혔다 |
| R7 | 탈퇴 요청 본문 | 사유가 필수가 됐으므로 `DELETE /v1/user`의 본문도 필수다. 본문 없이 호출하면 `VALIDATION_ERROR` |
| R8 | 분쟁 `기타` 문항 | `dispute_survey_questions`는 시드 마이그레이션이 없고 환경별로 직접 입력한다. 새 문항을 삽입하지 않고 백필만 하며, `기타` 문항을 등록할 때 `requires_detail = 1`로 넣어야 한다 |

## 정책 요약

```
reasonQuestionId 없음                        -> VALIDATION_ERROR("reasonQuestionId")
비활성/없는 reasonQuestionId                 -> VALIDATION_ERROR("reasonQuestionId")
reasonQuestionId 있음, requires_detail=false -> detailReason 선택
reasonQuestionId 있음, requires_detail=true  -> detailReason 필수
공백만 있는 detailReason                     -> VALIDATION_ERROR
```

적용 대상: `POST /v1/proposal/{id}/dispute`, `POST /v1/offer/{offerId}/dispute`,
`POST /v1/proposal/{id}/reports`, `DELETE /v1/user`.
환불(`refunds.reason`)은 사용자 입력이 아니라 시스템이 붙이는 원인 코드라 대상이 아니다.

## 실제 반영 내용

| 파일 | 작업 |
|---|---|
| `alembic/versions/0027_reason_detail_policy.py` | `requires_detail` 컬럼 2개 추가 + `기타` 백필, `dispute_evidences.reason` nullable 전환 |
| `app/models/dispute_survey.py`, `app/models/proposal_report.py` | `requires_detail` 컬럼 |
| `app/models/dispute_evidence.py` | `reason` nullable |
| `app/schemas/dispute_survey.py`, `app/schemas/proposal_report.py` | 질문 응답에 `requiresDetail` |
| `app/schemas/dispute_evidence.py`, `app/schemas/proposal_report.py`, `app/schemas/user.py` | 요청의 사유 필수·상세 선택, 응답의 `detailReason`만 nullable |
| `app/services/dispute/dispute_survey_service.py` | `resolve_reason()` 검증 헬퍼 |
| `app/services/proposal/proposal_report_service.py` | `_resolve_reason_question()`으로 `기타` 검증 추가 |
| `app/services/user_auth/user_withdrawal_service.py` | 사유 누락을 `VALIDATION_ERROR`로 거부 |
| `app/api/v1/user_auth/user_router.py` | 탈퇴 요청 본문 필수 |
| `app/core/openapi.py`, 각 라우터 description | 예시·문서 문구 갱신 |

요청 스키마의 `detailReason`은 공백 문자열을 거부하고 앞뒤 공백을 제거한다(탈퇴와 동일).

## 검증 근거

- [x] 분쟁: 사유 누락 → `VALIDATION_ERROR`, `기타` 상세 누락 → `VALIDATION_ERROR("detailReason")`,
      일반 사유는 상세 없이 접수, `기타`+상세는 접수
      (`test_raise_proposal_dispute_requires_detail_only_for_etc_reason`,
      `test_raise_proposal_dispute_accepts_etc_reason_with_detail`,
      `test_raise_offer_dispute_requires_detail_only_for_etc_reason`)
- [x] 신고: 사유 누락 → `VALIDATION_ERROR`, `기타` 상세 누락 → `VALIDATION_ERROR("detailReason")`
      (`test_create_proposal_report_requires_detail_only_for_etc_reason`)
- [x] 탈퇴: 본문 없음·사유 누락 → `VALIDATION_ERROR`, `기타` 상세 누락 → `VALIDATION_ERROR`
      (`test_withdraw_user_requires_reason_question_id`, `test_withdraw_user_requires_detail_for_other_reason`)
- [x] 질문 목록 응답에 `requiresDetail`이 포함된다
      (`test_list_proposal_report_reasons_returns_active_ordered_questions`,
      `test_list_user_withdrawal_reasons_returns_active_ordered_questions`, `test_openapi.py`)
- [x] `pytest`: 298 passed. 남은 2건은 이 변경 전 staging에서도 실패하던 기존 실패다
      (`test_create_proposal_validation_errors`,
      `test_withdraw_user_rolls_back_all_changes_when_anonymization_fails`)
- [x] `alembic upgrade head` → `downgrade -1` → `upgrade head` 왕복 확인

## 남은 리스크·후속

- `dispute_survey_questions`에는 시드 마이그레이션이 없다. 각 환경에서 `기타` 문항을 추가할 때
  `requires_detail = 1`로 넣어야 상세 사유가 강제된다.
- 탈퇴 사유가 선택에서 필수로 바뀌었다. 사유 없이 `DELETE /v1/user`를 호출하던 클라이언트는
  본문을 함께 보내도록 수정해야 한다.
- 분쟁 상세 사유는 `text` 컬럼이라 길이 제한이 없다. 신고·탈퇴(500자)와 다르지만 이번 변경에서는
  기존 동작을 좁히지 않았다.
