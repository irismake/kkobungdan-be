# 분쟁 사유 문항 시드 마이그레이션

작성일: 2026-08-26 · 상태: 구현 완료 · 근거 문서: [`./2026-08-26-reason-detail-policy.md`](./2026-08-26-reason-detail-policy.md)

## 배경

사유 마스터 3종 중 분쟁만 시드 마이그레이션이 없다. 신고는 `0015`, 탈퇴는 `0018`이 문항을 코드로
넣지만 `dispute_survey_questions`는 `0010`이 빈 테이블만 만들고 끝난다. 그래서 환경마다 사람이
직접 `INSERT`를 돌려야 하고, `기타` 문항에 `requires_detail = 1`을 빠뜨리면 컬럼 기본값 `0`이
적용돼 목록 응답의 `requiresDetail`이 `false`로 나간다. 클라이언트 제출 가드와 서버 검증이
동시에, 에러 없이 풀린다. `TD-009`로 추적하던 부채다.

staging 실데이터를 확인한 결과 문항은 ORDER 5개·RUNNER 5개이고 `기타`는 정확히 `기타`라
`0027`의 백필도 정상 적용돼 있다. 즉 지금 당장 깨진 환경은 없고, 위험은 "다음에 만들 환경"과
"손으로 넣는 다음 문항"에 있다.

## 결정 사항

| # | 항목 | 결정 |
|---|---|---|
| S1 | 정본 문구 | staging 현재 데이터를 그대로 정본으로 삼는다. 문구를 새로 만들지 않는다 |
| S2 | 삽입 조건 | `target_type`별로 행이 하나도 없을 때만 전체를 삽입한다. 이미 행이 있는 환경(staging·prod)은 건드리지 않는다 |
| S3 | 기존 환경 교정 | 행이 있는 환경에서는 `question_text`가 정본과 완전히 일치하는 행의 `requires_detail`만 정본 값으로 맞춘다 |
| S4 | 문구 추측 금지 | `LIKE '기타%'` 같은 부분 일치 교정은 하지 않는다. 문구 추측을 없애는 것이 `0027`의 목적이었고, 그 목적을 마이그레이션에서 되살리지 않는다 |
| S5 | downgrade | 아무것도 지우지 않는다. `dispute_evidences.survey_question_id`가 이 행들을 참조하므로 삭제하면 기존 분쟁 기록이 끊긴다 |

## 정책 요약

```
target_type에 행 0개  -> 정본 5개 삽입 (신규 환경: prod 초기 구축, 로컬, CI)
target_type에 행 있음 -> 삽입 없음. 문구 완전 일치 행의 requires_detail만 정본으로 UPDATE
downgrade             -> no-op (FK 참조 보호)
```

`uk_dispute_survey_questions_target_order`(`target_type` + `display_order`)가 UNIQUE라
무조건 삽입하면 기존 환경에서 마이그레이션이 깨진다. S2가 그것을 막는다.

## 정본 문항

| target_type | display_order | question_text | requires_detail |
|---|---|---|---|
| ORDER | 1 | 임무를 진행하기 어려워졌어요 | false |
| ORDER | 2 | 꼬봉과 연락이 되지 않아요 | false |
| ORDER | 3 | 임무 수행이 어렵다고 전달받았어요 | false |
| ORDER | 4 | 직접 해결하게 되었어요 | false |
| ORDER | 5 | 기타 | **true** |
| RUNNER | 1 | 행님과 연락이 되지 않아요 | false |
| RUNNER | 2 | 요청한 임무를 수행하기 어려워요 | false |
| RUNNER | 3 | 임무 내용이 변경되었어요 | false |
| RUNNER | 4 | 현장 상황으로 진행이 어려워요 | false |
| RUNNER | 5 | 기타 | **true** |

## 실제 반영 내용

| 파일 | 작업 |
|---|---|
| `alembic/versions/0028_seed_dispute_survey_questions.py` | 정본 문항 시드 + `requires_detail` 교정 |
| `docs/generated/db-schema.md` | "시드 마이그레이션이 없다" 문단 갱신 |
| `docs/exec-plans/tech-debt-tracker.md` | `TD-009` 해소 처리 |

## 검증 근거

로컬 scratch DB 2개(`orderrun_migtest`, `orderrun_migtest2`)로 확인한 뒤 drop했다.

- [x] 빈 DB에 `alembic upgrade head` → ORDER 5행·RUNNER 5행이 `id` 1~10으로 들어가고,
      `기타`(id 5, 10)만 `requires_detail = 1`. staging 실데이터와 문구·순서·플래그가 일치한다
- [x] `upgrade head` → `downgrade -1` → `upgrade head` 왕복에서 행이 늘거나 사라지지 않는다
      (ORDER 5행, RUNNER 5행 유지). downgrade가 no-op이고 upgrade가 행 수를 보고 건너뛴다
- [x] 문항이 이미 있는 DB(ORDER 5행·RUNNER 3행, 커스텀 문항 포함)에 적용 → 삽입 0건,
      행 수 그대로. `display_order`가 정본과 달라도 UNIQUE 충돌이 없다
- [x] 그 DB의 `기타`(ORDER, `requires_detail = 0`) → `1`로 교정. 이미 맞던 RUNNER `기타`와
      정본에 없는 커스텀 문항은 건드리지 않았다
- [x] `pytest`: 298 passed. 실패 2건(`test_create_proposal_validation_errors`,
      `test_withdraw_user_rolls_back_all_changes_when_anonymization_fails`)은 `0027` 시점에도
      있던 기존 실패다. 테스트는 `Base.metadata.create_all`로 스키마를 만들어 마이그레이션을 타지 않는다

## 남은 리스크·후속

- 문구를 바꿀 때는 이 마이그레이션이 아니라 새 마이그레이션을 쓴다. 이미 적용된 환경에는
  S2 때문에 재적용돼도 삽입이 일어나지 않는다.
- staging·prod에는 이 마이그레이션이 새로 넣는 행이 없다. 이미 문항이 있고 `requires_detail`도
  맞아서, 실제 효과는 "다음에 만들 환경"과 "정본이 코드에 남는 것"이다.
- `app/core/openapi.py`의 `DISPUTE_SURVEY_QUESTIONS_EXAMPLE`은 `러너의 수행 결과에 어떤 문제가
  있었나요?`라는, 설문 시절 문구를 예시로 쓴다. 실제 문항과 다르지만 이번 범위 밖이라 두었다.
- ~~`dispute_survey_questions.target_type`은 MySQL ENUM이라 `CLAUDE.md`의 ENUM 금지 규칙과
  어긋난다.~~ 해소됐다. [`2026-08-26-replace-mysql-enums-with-varchar.md`](./2026-08-26-replace-mysql-enums-with-varchar.md)에서
  남아 있던 ENUM 컬럼 6개를 함께 VARCHAR로 전환했다.
