from __future__ import annotations

import pytest

import ast
from pathlib import Path

from app.core.errors import ERRORS
from app.core.openapi import ROUTE_LEVEL_ERRORS
from app.main import app
from app.models.offer import OfferStatus


ALLOWED_SCHEMA_BASES = {"BaseModel", "Generic", "str", "Enum"}


@pytest.mark.scenario("API-TS-001")
def test_openapi_contains_korean_api_metadata():
    schema = app.openapi()

    assert schema["info"]["title"] == "OrderRun API"
    assert "OrderRun 백엔드 API" in schema["info"]["description"]


@pytest.mark.scenario("API-TS-002")
def test_user_alarm_openapi_exposes_only_patch():
    alarm_path = app.openapi()["paths"]["/v1/user/alarm"]

    assert set(alarm_path) == {"patch"}
    assert alarm_path["patch"]["summary"] == "알림 설정 변경"


@pytest.mark.scenario("API-TS-003")
def test_auth_signup_send_openapi_examples_match_response_shape():
    operation = app.openapi()["paths"]["/v1/auth/signup/send"]["post"]

    assert operation["summary"] == "회원가입 인증번호 발송"

    success_example = operation["responses"]["200"]["content"]["application/json"]["example"]
    assert success_example == {
        "success": True,
        "data": {"phone": "01012345678", "expiresAt": "2026-06-01T12:05:00+09:00"},
        "message": None,
    }

    conflict_examples = operation["responses"]["409"]["content"]["application/json"]["examples"]
    phone_exists = conflict_examples["PHONE_ALREADY_EXISTS"]["value"]
    assert phone_exists == {
        "success": False,
        "error": {
            "code": "PHONE_ALREADY_EXISTS",
            "message": "이미 가입된 휴대폰 번호입니다.",
            "details": None,
        },
        "timestamp": "2026-06-01T12:00:00+09:00",
    }


@pytest.mark.scenario("API-TS-004")
def test_validation_error_openapi_example_uses_standard_error_wrapper():
    operation = app.openapi()["paths"]["/v1/auth/login/confirm"]["post"]

    validation_example = operation["responses"]["400"]["content"]["application/json"]["examples"][
        "VALIDATION_ERROR"
    ]["value"]

    assert validation_example["success"] is False
    assert validation_example["error"]["code"] == "VALIDATION_ERROR"
    assert validation_example["timestamp"] == "2026-06-01T12:00:00+09:00"


@pytest.mark.scenario("API-TS-005")
def test_openapi_operations_have_success_examples_and_standard_error_examples():
    schema = app.openapi()

    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue

            responses = operation["responses"]
            assert "422" not in responses, f"{method.upper()} {path} documents FastAPI's default 422"

            success_codes = [code for code in responses if code.startswith("2")]
            assert success_codes, f"{method.upper()} {path} has no 2xx response"

            for code in success_codes:
                content = responses[code].get("content", {}).get("application/json")
                if code == "204":
                    assert content is None, f"{method.upper()} {path} 204 must not document a JSON body"
                    continue

                assert content is not None, f"{method.upper()} {path} {code} has no JSON content"
                assert "example" in content or "examples" in content, (
                    f"{method.upper()} {path} {code} has no success example"
                )
                if "examples" in content:
                    assert content["examples"], f"{method.upper()} {path} {code} has empty success examples"

            for code, response in responses.items():
                if not code.startswith(("4", "5")):
                    continue
                content = response.get("content", {}).get("application/json")
                assert content is not None, f"{method.upper()} {path} {code} has no JSON content"
                assert "examples" in content, f"{method.upper()} {path} {code} has no error examples"
                assert content["examples"], f"{method.upper()} {path} {code} has empty error examples"
                seen_error_cases = set()
                for example in content["examples"].values():
                    value = example["value"]
                    assert value["success"] is False
                    assert set(value["error"]) == {"code", "message", "details"}
                    assert value["error"]["code"]
                    assert value["error"]["message"]
                    assert value["timestamp"] == "2026-06-01T12:00:00+09:00"
                    error_case = (value["error"]["code"], value["error"]["message"])
                    assert error_case not in seen_error_cases, (
                        f"{method.upper()} {path} {code} has duplicate error example for {error_case}"
                    )
                    seen_error_cases.add(error_case)


@pytest.mark.scenario("API-TS-006")
def test_representative_success_examples_match_contracts():
    schema = app.openapi()

    proposal_create = schema["paths"]["/v1/proposal"]["post"]["responses"]["201"]["content"]["application/json"][
        "example"
    ]
    assert proposal_create["message"] == "요청이 등록되었습니다."
    assert proposal_create["data"]["status"] == "HOLDING"
    assert set(proposal_create["data"]) == {"id", "title", "content", "deadline", "errandFee", "status"}

    offer_accept = schema["paths"]["/v1/offer/{offer_id}/accept"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["example"]
    assert offer_accept["message"] == "지원이 수락되었습니다."
    assert offer_accept["data"]["proposalStatus"] == "MATCHED"
    assert "missionStatus" not in offer_accept["data"]
    assert "missionId" not in offer_accept["data"]
    assert "acceptedAt" in offer_accept["data"]
    assert {"runFee", "itemPrice", "totalAmount"}.isdisjoint(offer_accept["data"])

    proposal_detail_examples = schema["paths"]["/v1/proposal/{proposal_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]
    expected_proposal_statuses = {
        "holding": "HOLDING",
        "posted": "POSTED",
        "offered": "OFFERED",
        "matched": "MATCHED",
        "order_completed": "ORDER_COMPLETED",
        "all_completed": "ALL_COMPLETED",
        "disputed": "DISPUTED",
        "refund_pending": "REFUND_PENDING",
        "refunded": "REFUNDED",
        "cancelled": "CANCELLED",
    }
    assert set(proposal_detail_examples) == set(expected_proposal_statuses)

    for example_name, expected_status in expected_proposal_statuses.items():
        data = proposal_detail_examples[example_name]["value"]["data"]
        assert data["status"] == expected_status
        assert "missionId" not in data
        assert {
            "id",
            "title",
            "content",
            "deadline",
            "errandFee",
            "ordererId",
            "ordererName",
            "ordererLevel",
            "status",
            "offers",
        }.issubset(data)

    assert proposal_detail_examples["holding"]["value"]["data"]["offers"] == []
    assert proposal_detail_examples["posted"]["value"]["data"]["offers"] == []
    assert proposal_detail_examples["matched"]["value"]["data"]["matchedAt"] is not None
    assert proposal_detail_examples["order_completed"]["value"]["data"]["ordererConfirmedAt"] is not None
    assert proposal_detail_examples["all_completed"]["value"]["data"]["runnerConfirmedAt"] is not None
    assert "receivedConfirmedAt" not in proposal_detail_examples["order_completed"]["value"]["data"]
    assert "deliveryReportedAt" not in proposal_detail_examples["all_completed"]["value"]["data"]
    assert proposal_detail_examples["disputed"]["value"]["data"]["disputedAt"] is not None
    assert proposal_detail_examples["refund_pending"]["value"]["data"]["resolvedAt"] is not None

    offer_status_by_example = {
        "offered": "WAITING",
        "matched": "ACCEPTED",
        "order_completed": "ACCEPTED",
        "all_completed": "ALL_COMPLETED",
        "disputed": "DISPUTED",
        "refund_pending": "CANCELLED",
        "refunded": "CANCELLED",
        "cancelled": "CANCELLED",
    }
    for example_name, expected_offer_status in offer_status_by_example.items():
        offers = proposal_detail_examples[example_name]["value"]["data"]["offers"]
        assert len(offers) == 1
        assert set(offers[0]) == {
            "id",
            "proposalId",
            "runnerId",
            "runnerName",
            "runnerLevel",
            "status",
            "createdAt",
        }
        assert offers[0]["status"] == expected_offer_status

    offer_detail_examples = schema["paths"]["/v1/offer/{id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["examples"]
    expected_offer_statuses = {
        "waiting": "WAITING",
        "accepted": "ACCEPTED",
        "runner_completed": "RUNNER_COMPLETED",
        "all_completed": "ALL_COMPLETED",
        "disputed": "DISPUTED",
        "rejected": "REJECTED",
        "cancelled": "CANCELLED",
    }
    assert set(offer_detail_examples) == set(expected_offer_statuses)
    assert set(expected_offer_statuses.values()) == {status.value for status in OfferStatus}

    for example_name, expected_status in expected_offer_statuses.items():
        data = offer_detail_examples[example_name]["value"]["data"]
        assert data["status"] == expected_status
        assert {
            "id",
            "proposalId",
            "ordererId",
            "ordererName",
            "ordererLevel",
            "runnerId",
            "runnerName",
            "runnerLevel",
            "status",
            "createdAt",
        }.issubset(data)

    assert "missionId" not in offer_detail_examples["waiting"]["value"]["data"]
    assert "get" not in schema["paths"].get("/v1/offer/{offer_id}", {})
    assert offer_detail_examples["accepted"]["value"]["data"]["openChatUrl"] is not None
    assert offer_detail_examples["accepted"]["value"]["data"]["acceptedAt"] is not None
    assert offer_detail_examples["runner_completed"]["value"]["data"]["runnerConfirmedAt"] is not None
    assert offer_detail_examples["all_completed"]["value"]["data"]["ordererConfirmedAt"] is not None
    assert "matchedAt" not in offer_detail_examples["accepted"]["value"]["data"]
    assert "deliveryCompletedAt" not in offer_detail_examples["runner_completed"]["value"]["data"]
    assert "receiptConfirmedAt" not in offer_detail_examples["all_completed"]["value"]["data"]
    assert offer_detail_examples["disputed"]["value"]["data"]["disputedAt"] is not None

    for path in ("/v1/offer", "/v1/offer/own"):
        operation_examples = schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"][
            "examples"
        ]
        assert set(operation_examples) == set(expected_offer_statuses)
        runner_completed = operation_examples["runner_completed"]["value"]["data"]
        if path == "/v1/offer/own":
            runner_completed = runner_completed["content"][0]
        else:
            runner_completed = runner_completed[0]
        assert "acceptedAt" in runner_completed
        assert runner_completed["runnerConfirmedAt"] is not None
        assert "deliveryCompletedAt" not in runner_completed
        assert "receiptConfirmedAt" not in runner_completed

    offer_delivery_examples = schema["paths"]["/v1/offer/{offer_id}/complete-delivery"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["examples"]
    assert "requestBody" not in schema["paths"]["/v1/offer/{offer_id}/complete-delivery"]["post"]
    assert set(offer_delivery_examples) == {"runner_completed", "all_completed"}
    for example_name, expected_status in {
        "runner_completed": "RUNNER_COMPLETED",
        "all_completed": "ALL_COMPLETED",
    }.items():
        offer_delivery = offer_delivery_examples[example_name]["value"]
        assert offer_delivery["message"] == "완료 처리되었습니다."
        assert offer_delivery["data"]["status"] == expected_status
        assert "missionId" not in offer_delivery["data"]
        assert offer_delivery["data"]["runnerConfirmedAt"] is not None
        assert "deliveryCompletedAt" not in offer_delivery["data"]
        assert "receiptConfirmedAt" not in offer_delivery["data"]
    assert offer_delivery_examples["runner_completed"]["value"]["data"]["ordererConfirmedAt"] is None
    assert offer_delivery_examples["all_completed"]["value"]["data"]["ordererConfirmedAt"] is not None

    settlement = schema["paths"]["/v1/settlement/account"]["put"]["responses"]["200"]["content"]["application/json"][
        "example"
    ]
    assert settlement["message"] == "정산 계좌가 저장되었습니다."
    assert settlement["data"]["accountHolder"] == "홍길동"
    assert settlement["data"]["maskedAccountNumber"] == "********9012"
    assert "bankCode" not in settlement["data"]

    settlement_banks = schema["paths"]["/v1/settlement/banks"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["example"]
    assert "국민은행" in settlement_banks["data"]["bankNames"]

    notification = schema["paths"]["/v1/notifications/{notification_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["example"]
    assert notification["message"] == "Success"
    assert notification["data"]["notification_type"] == "custom"
    assert notification["data"]["status"] == "sent"


@pytest.mark.scenario("API-TS-007")
def test_nullable_fields_stay_visible_in_examples():
    """값이 null인 필드가 예시에서 사라지면 안 된다.

    FastAPI가 스키마를 exclude_none으로 인코딩하기 때문에 후처리로 되돌린다.
    이 테스트가 깨지면 클라이언트가 nullable 필드를 문서에서 볼 수 없게 된다.
    """
    schema = app.openapi()

    mission = schema["paths"]["/v1/admin/missions"]["get"]["responses"]["200"]["content"]["application/json"][
        "examples"
    ]["started"]["value"]["data"]["content"][0]
    for field in ("resolution", "runnerConfirmedAt", "disputedAt", "resolvedAt", "payoutMemo"):
        assert field in mission, field
        assert mission[field] is None
    assert mission["openChatUrl"] == "https://open.kakao.com/o/example"
    assert {"refunded", "refundedAt", "refundedByAdminId"}.isdisjoint(mission)

    report = schema["paths"]["/v1/admin/proposal-reports"]["get"]["responses"]["200"]["content"]["application/json"][
        "examples"
    ]["pending"]["value"]["data"]["content"][0]
    assert report["reviewedAt"] is None

    signup = schema["paths"]["/v1/auth/signup/send"]["post"]["responses"]["200"]["content"]["application/json"][
        "example"
    ]
    assert signup["message"] is None


@pytest.mark.scenario("API-TS-008")
def test_auth_login_confirm_request_exposes_explicit_fields():
    schema = app.openapi()["components"]["schemas"]["AuthLoginConfirmRequest"]

    assert set(schema["properties"]) == {"phone", "code", "fcmToken"}


@pytest.mark.scenario("API-TS-009")
def test_admin_confirm_payment_requires_open_chat_url():
    operation = app.openapi()["paths"]["/v1/admin/proposal/{proposal_id}/confirm-payment"]["post"]

    assert operation["requestBody"]["required"] is True
    schema = app.openapi()["components"]["schemas"]["AdminConfirmPaymentRequest"]
    assert set(schema["properties"]) == {"openChatUrl"}
    assert schema["required"] == ["openChatUrl"]


@pytest.mark.scenario("API-TS-010")
def test_refund_is_completed_only_through_refund_resource():
    paths = app.openapi()["paths"]

    assert "/v1/admin/missions/{mission_id}/refund" not in paths
    assert "/v1/admin/refund/{refund_id}/reject" not in paths


@pytest.mark.scenario("API-TS-011")
def test_admin_proposal_contracts_use_dedicated_response_schemas():
    schemas = app.openapi()["components"]["schemas"]

    assert set(schemas["AdminProposalResponse"]["properties"]) == set(schemas["ProposalResponse"]["properties"])
    assert set(schemas["AdminProposalReportResponse"]["properties"]) == set(
        schemas["ProposalReportResponse"]["properties"]
    )


@pytest.mark.scenario("API-TS-012")
def test_admin_participant_names_are_required_non_nullable_strings():
    schemas = app.openapi()["components"]["schemas"]
    required_names = {
        "MissionResponse": {"ordererName", "runnerName"},
        "AdminProposalReportResponse": {"reporterName"},
        "AdminProposalSummaryResponse": {"ordererName"},
        "AdminProposalDetailResponse": {"ordererName"},
        "AdminOfferSummaryResponse": {"runnerName"},
        "AdminDisputeSummaryResponse": {"requesterName"},
        "AdminDisputeDetailResponse": {"requesterName", "targetName"},
        "AdminRefundSummaryResponse": {"ordererName"},
        "AdminRefundDetailResponse": {"ordererName"},
        "AdminPayoutDetailResponse": {"runnerName"},
    }

    for schema_name, fields in required_names.items():
        schema = schemas[schema_name]
        assert fields <= set(schema["required"])
        for field in fields:
            assert schema["properties"][field]["type"] == "string"

    assert "acceptedRunnerName" not in schemas["AdminProposalDetailResponse"]["required"]


@pytest.mark.scenario("API-TS-013")
def test_admin_payout_list_uses_mission_response_with_settlement_status():
    schema = app.openapi()
    mission_schema = schema["components"]["schemas"]["MissionResponse"]
    assert "settlementStatus" in mission_schema["properties"]
    assert "AdminPayoutSummaryResponse" not in schema["components"]["schemas"]

    item = schema["paths"]["/v1/admin/payout"]["get"]["responses"]["200"]["content"]["application/json"][
        "example"
    ]["data"]["content"][0]
    assert item["settlementStatus"] == "PENDING"
    assert item["status"] == "COMPLETED"


@pytest.mark.scenario("API-TS-014")
def test_proposal_and_offer_creation_document_required_settlement_account():
    schema = app.openapi()
    for path in ("/v1/proposal", "/v1/offer"):
        examples = schema["paths"][path]["post"]["responses"]["409"]["content"]["application/json"]["examples"]
        codes = {example["value"]["error"]["code"] for example in examples.values()}
        assert "SETTLEMENT_ACCOUNT_REQUIRED" in codes


@pytest.mark.scenario("API-TS-015")
def test_offer_accept_has_no_request_body_or_amount_response_fields():
    operation = app.openapi()["paths"]["/v1/offer/{offer_id}/accept"]["post"]

    assert "requestBody" not in operation
    response_ref = operation["responses"]["201"]["content"]["application/json"]["schema"]["$ref"]
    response_name = response_ref.rsplit("/", 1)[-1]
    data_schema = app.openapi()["components"]["schemas"][response_name]["properties"]["data"]
    accept_ref = next(item["$ref"] for item in data_schema["anyOf"] if "$ref" in item)
    accept_name = accept_ref.rsplit("/", 1)[-1]
    accept_schema = app.openapi()["components"]["schemas"][accept_name]

    assert {"runFee", "itemPrice", "totalAmount"}.isdisjoint(accept_schema["properties"])


@pytest.mark.scenario("API-TS-016")
def test_dispute_requests_require_reason_question_id_only():
    """사유 선택은 필수이고 상세 사유는 기타 사유에서만 필수라 스키마 required에는 사유만 남는다."""
    schema = app.openapi()
    targets = [
        ("/v1/proposal/{proposal_id}/dispute", "post"),
        ("/v1/offer/{offer_id}/dispute", "post"),
        ("/v1/proposal/{proposal_id}/reports", "post"),
        ("/v1/user", "delete"),
    ]

    for path, method in targets:
        operation = schema["paths"][path][method]
        request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
        request_name = request_schema["$ref"].rsplit("/", 1)[-1]
        body_schema = schema["components"]["schemas"][request_name]

        assert set(body_schema["required"]) == {"reasonQuestionId"}
        assert body_schema["properties"]["reasonQuestionId"]["minimum"] == 1


@pytest.mark.scenario("API-TS-017")
def test_dispute_evidence_lookup_is_documented_with_exclusive_query_params():
    operation = app.openapi()["paths"]["/v1/dispute-evidence"]["get"]
    params = {param["name"]: param for param in operation["parameters"]}

    assert set(params) == {"proposalId", "offerId"}
    assert params["proposalId"]["required"] is False
    assert params["offerId"]["required"] is False
    assert operation["responses"]["200"]["content"]["application/json"]["example"]["data"] == {
        "id": 1,
        "proposalId": 1,
        "offerId": 10,
        "actorId": "550e8400-e29b-41d4-a716-446655440001",
        "reasonQuestionId": 3,
        "reasonQuestionText": "물건이 파손되었어요",
        "detailReason": "배송 중 파손",
        "createdAt": "2026-06-01T12:00:00+09:00",
    }


@pytest.mark.scenario("API-TS-018")
def test_mission_collection_get_is_not_documented():
    mission_collection = app.openapi()["paths"].get("/v1/mission")

    assert mission_collection is None or "get" not in mission_collection


@pytest.mark.scenario("API-TS-019")
def test_list_status_filters_are_repeatable_array_query_parameters():
    schema = app.openapi()
    targets = [
        ("/v1/proposal", "get"),
        ("/v1/proposal/own", "get"),
        ("/v1/offer", "get"),
        ("/v1/offer/own", "get"),
    ]

    for path, method in targets:
        operation = schema["paths"][path][method]
        status_param = next(parameter for parameter in operation["parameters"] if parameter["name"] == "status")
        array_schema = next(item for item in status_param["schema"]["anyOf"] if item.get("type") == "array")

        assert status_param["in"] == "query"
        assert array_schema["items"]["$ref"].startswith("#/components/schemas/")
        assert "status=A&status=B" in status_param["description"]


@pytest.mark.scenario("API-TS-020")
def test_api_schemas_do_not_inherit_from_other_api_dtos():
    schema_dir = Path(__file__).resolve().parents[1] / "app" / "schemas"
    violations: list[str] = []

    for path in schema_dir.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                base_name = _base_name(base)
                if base_name and base_name not in ALLOWED_SCHEMA_BASES:
                    violations.append(f"{path.name}:{node.name}({base_name})")

    assert violations == []


def _base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return None


def _error_codes_in_openapi() -> set[str]:
    codes: set[str] = set()
    for path_item in app.openapi()["paths"].values():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            for status_code, response in operation.get("responses", {}).items():
                if not str(status_code).startswith(("4", "5")):
                    continue
                content = response.get("content", {}).get("application/json", {})
                for example in content.get("examples", {}).values():
                    codes.add(example["value"]["error"]["code"])
    return codes


@pytest.mark.scenario("API-TS-021")
def test_every_catalog_error_code_appears_in_openapi():
    """카탈로그에 코드를 추가하면 어떤 엔드포인트든 문서화하도록 강제한다."""
    route_level = {ERRORS[error].code for error in ROUTE_LEVEL_ERRORS}
    expected = {spec.code for spec in ERRORS.values()} - route_level

    missing = expected - _error_codes_in_openapi()

    assert not missing, f"openapi.json에 없는 에러 코드: {sorted(missing)}"


@pytest.mark.scenario("API-TS-022")
def test_route_level_errors_are_documented_in_api_description():
    """오퍼레이션에 붙일 수 없는 전역 코드는 API 설명에 남아 있어야 한다."""
    description = app.openapi()["info"]["description"]

    for error in ROUTE_LEVEL_ERRORS:
        assert ERRORS[error].code in description


@pytest.mark.scenario("API-TS-023")
def test_internal_server_error_is_declared_on_every_operation():
    for path, path_item in app.openapi()["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            examples = (
                operation["responses"]["500"]["content"]["application/json"]["examples"]
            )
            codes = {example["value"]["error"]["code"] for example in examples.values()}
            assert "INTERNAL_SERVER_ERROR" in codes, f"{method.upper()} {path}"
