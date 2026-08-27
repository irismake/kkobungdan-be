# MySQL native ENUM 제거와 non-native Enum + CHECK 제약 도입

작성일: 2026-08-26 · 상태: 구현 완료 · 근거 문서: [`../../../CLAUDE.md`](../../../CLAUDE.md) "No MySQL native ENUM types"

## 배경

`CLAUDE.md`는 DB 컬럼에 MySQL native `ENUM`을 쓰지 않는다고 못박고 있다. 값을 추가할 때마다
`ALTER TABLE`이 필요하고, 마이그레이션이 복잡해지며, MySQL 버전별 동작 차이가 있기 때문이다.
[`0026_create_refunds`](../../../alembic/versions/0026_create_refunds.py)가 그 비용을 그대로 치렀다.
`proposals.status`에 값 2개를 더하려고 11개 값 전체를 다시 나열해 `MODIFY status ENUM(...)`을 돌렸고,
구·신 값 목록을 `EXPANDED_PROPOSAL_STATUSES`·`PROPOSAL_STATUSES`·`OLD_OFFER_STATUSES`로 나눠
관리해야 했다. 241줄짜리 마이그레이션이 나왔다.

문제가 눈에 안 띄었던 이유가 있다. SQLAlchemy의 `Enum(PythonEnum)`은 **generic 렌더링이
`VARCHAR(n)`**이라 모델을 읽거나 `str(column.type)`을 찍으면 VARCHAR처럼 보인다. MySQL DDL만
`enum(...)`이었다. 그래서 `docs/generated/db-schema.md`는 `varchar(20)`이라 적고 있었고,
`test_dispute_survey_question_model_spec_matches_plan`은 `VARCHAR(6)`을 통과시키고 있었다.
문서·테스트·모델이 전부 VARCHAR라고 말하는데 DB만 ENUM이었다.

## 결정 사항

| # | 항목 | 결정 |
|---|---|---|
| E1 | DB 타입 | native ENUM으로 남아 있던 컬럼 6개를 전부 `VARCHAR`로 전환한다 |
| E2 | 모델 매핑 | `Enum(PythonEnum, native_enum=False, create_constraint=True, name="ck_<table>_<column>_values", values_callable=..., length=n)`. DB에는 `VARCHAR` + `CHECK`로 저장하고 애플리케이션에는 Python Enum을 돌려준다 |
| E3 | 공통 헬퍼 | 같은 인자 11벌을 반복하지 않도록 `app/models/enum_type.py`의 `enum_column(enum_class, length, table=, column=)`로 한 곳에 모은다. 제약 이름 규약도 여기서 만든다 |
| E4 | 적용 범위 | native ENUM이었던 6개에 더해, 이미 `String(n)`이라 앱에 `str`을 돌려주던 상태 컬럼 5개도 같은 매핑으로 맞춘다 |
| E5 | 값 검증 | `create_constraint=True`로 이름 붙인 `CHECK` 제약(`ck_<table>_<column>_values`)을 걸어 DB가 허용값을 강제한다. 애플리케이션에서는 Pydantic이 이중으로 막는다 |
| E6 | 제약 갱신 | 상태값을 추가·제거·변경할 때는 `CHECK`를 갱신하는 마이그레이션을 반드시 함께 쓴다 |
| E7 | downgrade | ENUM으로 되돌리거나 `CHECK`를 걸 때 목록 밖의 값이 있으면 중단하고 어떤 값이 걸리는지 알려준다 |

E4가 중요하다. 6개만 바꾸면 `proposal.status`는 Python Enum, `mission.status`는 `str`이 되어
같은 코드베이스 안에 두 규약이 공존한다. 아래 표의 함정이 절반의 컬럼에만 적용되는 상태가
제일 위험하다.

## 전환한 컬럼

**native ENUM → VARCHAR** (마이그레이션 `0029` 필요)

| 테이블 | 컬럼 | 이전 | 이후 |
|---|---|---|---|
| `auth_phone_verifications` | `purpose` | `enum('SIGNUP','LOGIN')` | `varchar(10)` |
| `auth_phone_verifications` | `status` | `enum(...)` 3종 | `varchar(20)` |
| `dispute_survey_questions` | `target_type` | `enum('ORDER','RUNNER')` | `varchar(10)` |
| `offers` | `status` | `enum(...)` 7종 | `varchar(20)` |
| `proposal_reports` | `status` | `enum(...)` 3종 | `varchar(20)` |
| `proposals` | `status` | `enum(...)` 11종 | `varchar(20)` |

**모델 매핑만 교체** (DB 타입 동일. 타입 변경 마이그레이션은 불필요하고 `CHECK` 제약은 `0030`이 건다)

| 테이블 | 컬럼 | 이전 | 이후 |
|---|---|---|---|
| `missions` | `status` | `String(20)` + `.value` | `enum_column(MissionStatus, 20, ...)` |
| `missions` | `resolution` | `String(20)` | `enum_column(MissionResolution, 20, ...)` |
| `refunds` | `status` | `String(20)` + `.value` | `enum_column(RefundStatus, 20, ...)` |
| `refunds` | `reason` | `String(30)` | `enum_column(RefundReason, 30, ...)` |
| `dispute_evidences` | `status` | `String(20)` + `.value` | `enum_column(DisputeProcessStatus, 20, ...)` |

## 왜 plain `String(n)`이 아닌가

처음에는 `String(n)` + 호출부 `.value` 규약으로 갔다가 되돌렸다. 컬럼이 `String`이면 ORM이 읽어
오는 값이 열거형 멤버가 아니라 **plain `str`**이 되고, 거기서 동작이 갈린다.

| 패턴 | plain `String` | non-native `Enum` |
|---|---|---|
| `obj.status = Status.X` | 정상 | 정상 |
| `Model.status == Status.X` (SQL) | 정상 | 정상 |
| `obj.status == Status.X` (파이썬) | 정상 | 정상 |
| `obj.status in (A, B)` (튜플) | 정상 | 정상 |
| **`obj.status in {A, B}` (집합)** | **조용히 `False`** | 정상 |
| **`obj.status.value`** | **`AttributeError`** | 정상 |

집합 멤버십이 특히 나쁘다. `.value`는 예외가 나서 테스트가 잡지만, 집합은 에러 없이 `False`로
빠져 상태 전이가 조용히 막힌다. `Enum.__hash__`가 이름 기준이라 `str`과 해시가 다르기 때문이다.
plain `String`으로 가면 이 함정을 피하려고 호출부 195곳에 `.value`를 붙여야 했다.
non-native Enum 매핑은 DDL만 VARCHAR로 바꾸고 애플리케이션 타입은 그대로 두므로
**호출부 수정이 0곳**이다.

## 실제 반영 내용

| 파일 | 작업 |
|---|---|
| `alembic/versions/0029_replace_mysql_enums_with_varchar.py` | 6개 컬럼 `MODIFY COLUMN` + downgrade 가드 |
| `alembic/versions/0030_enum_check_constraints.py` | 열거형 컬럼 11개에 이름 붙인 `CHECK` 제약 + 위반값 가드 |
| `app/models/enum_type.py` | `enum_column()`·`check_constraint_name()` 헬퍼 신규 |
| `app/models/{user,proposal,offer,proposal_report,dispute_survey}.py` | native ENUM 6개를 `enum_column`으로 |
| `app/models/{mission,refund,dispute_evidence}.py` | `String(n)`이던 상태 컬럼 5개를 `enum_column`으로, 기본값을 열거형 멤버로 |
| `app/services/**` | 위 5개 컬럼을 `str`로 가정하던 `.value` 29곳 제거 |
| `app/models/mission.py` | `self.status in {status.value for ...}` → `in TERMINAL_STATUSES` |
| `tests/test_dispute_survey_integration.py` | `VARCHAR(6)` → `VARCHAR(10)` 기대값, `CHECK` 제약 선언·강제 회귀 테스트 2건 |
| `docs/generated/db-schema.md` | 규약 명시, `purpose`·`target_type`·`proposal_reports.status` 타입 정정 |

## 검증 근거

- [x] `alembic upgrade head` 후 `information_schema`에 ENUM 컬럼 **0건**
- [x] 모델이 만드는 DDL이 `status VARCHAR(20) NOT NULL`. 열거형 컬럼 11개 전부 DB 타입과 일치
- [x] 왕복 실측: `DisputeSurveyTargetType.ORDER`를 저장하면 DB에는 `'ORDER'` 문자열이 들어가고,
      읽으면 `<DisputeSurveyTargetType.ORDER>` 멤버가 나온다. `.value`·집합 멤버십·멤버 필터 모두 정상
- [x] 전환 후에도 데이터 보존. `dispute_survey_questions` 10행이 문구·플래그 그대로 남는다
- [x] `ix_proposals_status` 등 인덱스가 `MODIFY COLUMN` 이후에도 유지된다
- [x] `upgrade head` → `downgrade -1` → `upgrade head` 왕복. downgrade가 ENUM을 정확히 복원한다
- [x] downgrade 가드: `target_type`에 `PARTNER`를 넣고 되돌리면 `RuntimeError`로 중단된다.
      가드가 없으면 strict mode(MySQL 8 기본)에서 `ERROR 1265`로, non-strict mode에서는 빈 문자열
      절삭으로 끝난다
- [x] `CHECK` 제약 11개가 `ck_<table>_<column>_values` 이름으로 생성된다
- [x] `INSERT ... VALUES ('PARTNER', ...)`가 `ERROR 3819 Check constraint ... is violated`로 거부된다.
      앱을 우회한 수동 SQL도 막힌다
- [x] `0030` 왕복: downgrade 후 `CHECK` 0건, 재적용 후 11건
- [x] `0030` 가드: 목록 밖의 값이 남아 있으면 `RuntimeError`로 중단하며 걸리는 값(`['PARTNER']`)을 알려준다
- [x] 상태값 추가는 `CHECK` 갱신 마이그레이션이 필요하다. MySQL native ENUM과 달리 컬럼 타입 변경이
      아니라 제약 교체라 테이블 재작성이 없다
- [x] `pytest`: 298 passed. 실패 2건(`test_create_proposal_validation_errors`,
      `test_withdraw_user_rolls_back_all_changes_when_anonymization_fails`)은 착수 전과 동일한 기존 실패다

## 남은 리스크·후속

- **DB 레벨 값 검증은 `CHECK` 제약으로 유지된다.** native ENUM을 버리면서 잃을 뻔했던 무결성을
  이름 붙인 제약으로 되찾았다. 대신 상태값을 바꿀 때 제약 갱신 마이그레이션을 빠뜨리면 새 값이
  DB에서 거부된다. 모델과 제약이 어긋나는 이 실패는 배포 후 런타임에 드러나므로,
  상태값 변경 PR에서는 마이그레이션 동반 여부를 반드시 확인해야 한다.
- MySQL 8.0.16 미만은 `CHECK`를 파싱만 하고 무시한다. 현재 로컬·staging은 그 위 버전이지만,
  DB 버전을 내리면 이 무결성 보장이 조용히 사라진다.
- `MODIFY COLUMN`은 테이블을 다시 쓴다. 현재 규모에서는 순간이지만 데이터가 커지면 배포 시점을
  고려해야 한다.
- `alembic check`는 이 저장소에서 게이트로 쓸 수 없다. `alembic/env.py`가 `proposal_report` 모델을
  import하지 않아 해당 테이블이 삭제 대상으로 잡히는 등 기존 드리프트가 있다. 이번 변경과 무관한
  선행 문제라 손대지 않았다.
