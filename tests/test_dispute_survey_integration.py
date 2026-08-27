from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models.dispute_evidence import DisputeEvidence
from app.models.dispute_survey import DisputeSurveyQuestion, DisputeSurveyTargetType


def _question(
    target_type: DisputeSurveyTargetType,
    question_text: str,
    display_order: int,
    is_active: bool = True,
) -> DisputeSurveyQuestion:
    return DisputeSurveyQuestion(
        target_type=target_type,
        question_text=question_text,
        display_order=display_order,
        is_active=is_active,
    )


def test_list_order_dispute_survey_questions_returns_active_questions_in_display_order(client, db, auth_headers):
    older = _question(DisputeSurveyTargetType.ORDER, "두 번째 오더 질문", 2)
    first = _question(DisputeSurveyTargetType.ORDER, "첫 번째 오더 질문", 1)
    runner = _question(DisputeSurveyTargetType.RUNNER, "러너 질문", 1)
    inactive = _question(DisputeSurveyTargetType.ORDER, "비활성 질문", 3, is_active=False)
    db.add_all([older, first, runner, inactive])
    db.commit()

    response = client.get("/v1/dispute-survey/questions?targetType=ORDER", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Success"
    assert [item["questionText"] for item in body["data"]] == ["첫 번째 오더 질문", "두 번째 오더 질문"]
    assert [item["displayOrder"] for item in body["data"]] == [1, 2]
    assert {item["targetType"] for item in body["data"]} == {"ORDER"}


def test_list_runner_dispute_survey_questions_returns_runner_questions_only(client, db, auth_headers):
    db.add_all(
        [
            _question(DisputeSurveyTargetType.ORDER, "오더 질문", 1),
            _question(DisputeSurveyTargetType.RUNNER, "첫 번째 러너 질문", 1),
            _question(DisputeSurveyTargetType.RUNNER, "두 번째 러너 질문", 2),
        ]
    )
    db.commit()

    response = client.get("/v1/dispute-survey/questions?targetType=RUNNER", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert [item["questionText"] for item in body["data"]] == ["첫 번째 러너 질문", "두 번째 러너 질문"]
    assert {item["targetType"] for item in body["data"]} == {"RUNNER"}


def test_list_dispute_survey_questions_returns_empty_list(client, auth_headers):
    response = client.get("/v1/dispute-survey/questions?targetType=ORDER", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"success": True, "data": [], "message": "Success"}


def test_list_dispute_survey_questions_validation_and_auth_errors(client, auth_headers):
    invalid_target = client.get("/v1/dispute-survey/questions?targetType=CUSTOMER", headers=auth_headers)
    assert invalid_target.status_code == 400
    assert invalid_target.json()["error"]["code"] == "VALIDATION_ERROR"

    no_token = client.get("/v1/dispute-survey/questions?targetType=ORDER")
    assert no_token.status_code == 401
    assert no_token.json()["error"]["code"] == "INVALID_TOKEN"


def test_dispute_survey_question_model_spec_matches_plan():
    table = DisputeSurveyQuestion.__table__

    assert str(table.c.id.type).upper() == "BIGINT"
    # MySQL ENUM을 쓰지 않는다(CLAUDE.md). 값이 하나 늘어날 때 ALTER TABLE을 하지 않도록
    # RUNNER(6자)에 여유를 둔 VARCHAR(10)이다.
    assert str(table.c.target_type.type).upper() == "VARCHAR(10)"
    assert str(table.c.question_text.type).upper() == "VARCHAR(500)"
    assert table.c.is_active.nullable is False
    assert table.foreign_keys == set()

    unique_names = {constraint.name for constraint in table.constraints}
    index_names = {index.name for index in table.indexes}
    assert "uk_dispute_survey_questions_target_order" in unique_names
    assert "idx_dispute_survey_questions_lookup" in index_names


def test_enum_column_declares_named_check_constraint():
    """CLAUDE.md: 상태 컬럼은 VARCHAR + 이름 붙인 CHECK로 허용값을 고정한다."""
    table = DisputeSurveyQuestion.__table__

    checks = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }
    assert "ck_dispute_survey_questions_target_type_values" in checks


def test_enum_check_constraint_rejects_value_outside_the_enum(db):
    """DB가 열거형 밖의 값을 실제로 거부한다. 앱을 우회한 SQL도 막혀야 한다."""
    with pytest.raises((IntegrityError, OperationalError)):
        db.execute(
            sa.text(
                "INSERT INTO dispute_survey_questions "
                "(target_type, question_text, display_order, is_active, requires_detail, created_at, updated_at) "
                "VALUES ('PARTNER', '열거형 밖의 값', 99, 1, 0, NOW(), NOW())"
            )
        )
    db.rollback()


def test_dispute_evidence_model_requires_survey_question_and_mission():
    table = DisputeEvidence.__table__

    # 사유 선택은 필수, 상세 사유는 기타 사유에서만 필수라 컬럼은 nullable이다.
    assert str(table.c.survey_question_id.type).upper() == "BIGINT"
    assert table.c.survey_question_id.nullable is False
    assert table.c.reason.nullable is True
    assert str(table.c.mission_id.type).upper() == "BIGINT"
    assert table.c.mission_id.nullable is False
    index_names = {index.name for index in table.indexes}
    assert "idx_dispute_evidences_survey_question_id" in index_names
    assert "idx_dispute_evidences_mission_id" in index_names
    assert any(
        foreign_key.parent.name == "mission_id" and foreign_key.target_fullname == "missions.id"
        for foreign_key in table.foreign_keys
    )
