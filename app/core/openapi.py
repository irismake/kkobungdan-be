"""OpenAPI response example helpers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from copy import deepcopy
from typing import Any

from app.core.errors import AppError, ERRORS
from app.schemas.common import ErrorResponse


EXAMPLE_TIMESTAMP = "2026-06-01T12:00:00+09:00"


# 특정 엔드포인트가 아니라 앱 전역에서 발생하는 에러.
# INTERNAL_SERVER_ERROR는 어느 엔드포인트에서든 날 수 있으므로 모든 오퍼레이션에 주입한다.
# NOT_FOUND·METHOD_NOT_ALLOWED는 매칭되는 오퍼레이션이 없을 때만 발생해 특정 오퍼레이션에
# 속할 수 없으므로, 주입하지 않고 API 설명에 문서화한다.
GLOBAL_OPERATION_ERRORS: tuple[AppError, ...] = (AppError.INTERNAL_SERVER_ERROR,)
ROUTE_LEVEL_ERRORS: tuple[AppError, ...] = (AppError.NOT_FOUND, AppError.METHOD_NOT_ALLOWED)


def _iter_routes(routes: Iterable[Any], prefix: str = "") -> Iterable[tuple[str, Any]]:
    """중첩된 라우터를 펼쳐 (전체 경로, 라우트) 쌍을 내놓는다.

    `include_router()`가 라우터를 원본 그대로 감싸 넣고 접두사는 매칭 시점에 붙이므로,
    `app.routes`는 평평하지 않고 개별 라우트의 경로에도 접두사가 없다. 감싼 층을 따라
    내려가며 접두사를 모아 스키마의 경로 키와 맞춘다.
    """
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            context = getattr(route, "include_context", None)
            yield from _iter_routes(included.routes, prefix + (getattr(context, "prefix", "") or ""))
            continue
        path_format = getattr(route, "path_format", None)
        if path_format is not None:
            yield prefix + path_format, route


def restore_example_nulls(schema: dict[str, Any], routes: Iterable[Any]) -> None:
    """라우트에 선언한 응답 예시를 인코딩 전 원본으로 되돌린다.

    FastAPI의 `get_openapi()`는 스키마를 `exclude_none`으로 인코딩하므로 값이 `None`인
    필드가 예시에서 통째로 사라진다. 클라이언트는 문서만 보고 응답에 어떤 필드가 오는지
    알아야 하므로, 생성이 끝난 뒤 원본 예시를 다시 넣는다.

    `content."application/json"`의 `example`·`examples`만 덮어쓴다. FastAPI가 채운
    스키마 참조 등 나머지는 건드리지 않는다.
    """
    paths = schema.get("paths", {})
    for path, route in _iter_routes(routes):
        declared = getattr(route, "responses", None)
        path_item = paths.get(path)
        if not declared or not path_item:
            continue

        for method in getattr(route, "methods", None) or ():
            operation = path_item.get(method.lower())
            if not isinstance(operation, dict):
                continue
            for status, response in declared.items():
                target = operation.get("responses", {}).get(str(status))
                source = response.get("content", {}).get("application/json", {})
                if not isinstance(target, dict) or not source:
                    continue
                json_content = target.setdefault("content", {}).setdefault("application/json", {})
                for key in ("example", "examples"):
                    if key in source:
                        json_content[key] = deepcopy(source[key])


def apply_global_error_responses(schema: dict[str, Any]) -> None:
    """Attach app-wide error responses to every operation in a generated schema."""
    has_error_model = "ErrorResponse" in schema.get("components", {}).get("schemas", {})

    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            for error in GLOBAL_OPERATION_ERRORS:
                spec = ERRORS[error]
                response = operation["responses"].setdefault(
                    str(spec.http_status),
                    {"description": "실패 응답", "content": {"application/json": {}}},
                )
                json_content = response.setdefault("content", {}).setdefault("application/json", {})
                if has_error_model:
                    json_content.setdefault("schema", {"$ref": "#/components/schemas/ErrorResponse"})
                json_content.setdefault("examples", {}).setdefault(
                    error.value,
                    {"summary": spec.code, "value": error_response_example(error)},
                )


def error_response_example(error: AppError, details: str | None = None) -> dict[str, Any]:
    spec = ERRORS[error]
    return {
        "success": False,
        "error": {
            "code": spec.code,
            "message": spec.message,
            "details": details,
        },
        "timestamp": EXAMPLE_TIMESTAMP,
    }


def error_responses(*errors: AppError) -> dict[int | str, dict[str, Any]]:
    expanded_errors = list(errors)
    if AppError.INVALID_TOKEN in expanded_errors:
        for auth_error in (
            AppError.MISSING_CREDENTIALS,
            AppError.INVALID_TOKEN_CREDENTIALS,
            AppError.INVALID_TOKEN_TYPE,
            AppError.INVALID_AUTHENTICATION_CREDENTIALS,
        ):
            if auth_error not in expanded_errors:
                expanded_errors.append(auth_error)

    grouped: dict[int, list[AppError]] = defaultdict(list)
    for error in expanded_errors:
        grouped[ERRORS[error].http_status].append(error)

    responses: dict[int | str, dict[str, Any]] = {}
    for http_status, status_errors in grouped.items():
        responses[http_status] = {
            "model": ErrorResponse,
            "description": "실패 응답",
            "content": {
                "application/json": {
                    "examples": {
                        error.value: {
                            "summary": ERRORS[error].code,
                            "value": error_response_example(error),
                        }
                        for error in status_errors
                    }
                }
            },
        }

    return responses


def success_response(example: dict[str, Any], description: str = "성공 응답") -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "example": example,
            }
        },
    }


def success_response_examples(examples: dict[str, dict[str, Any]], description: str = "성공 응답") -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "examples": {
                    key: {
                        "summary": key,
                        "value": value,
                    }
                    for key, value in examples.items()
                }
            }
        },
    }


def no_content_response(description: str = "성공 응답") -> dict[str, Any]:
    return {"description": description}


VALIDATION_ERROR_RESPONSE = error_responses(AppError.VALIDATION_ERROR)
AUTH_ERROR_RESPONSES = error_responses(AppError.INVALID_TOKEN)

EXAMPLE_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
EXAMPLE_RUNNER_ID = "550e8400-e29b-41d4-a716-446655440001"
EXAMPLE_ORDERER_NAME = "홍길동"
EXAMPLE_RUNNER_NAME = "Runner One"
EXAMPLE_ORDERER_LEVEL = 0
EXAMPLE_RUNNER_LEVEL = 3
EXAMPLE_CREATED_AT = "2026-06-01T12:00:00+09:00"
EXAMPLE_UPDATED_AT = "2026-06-01T12:10:00+09:00"
EXAMPLE_DEADLINE = "2026-06-02T12:00:00+09:00"

USER_DETAIL_EXAMPLE = {
    "success": True,
    "data": {
        "id": EXAMPLE_USER_ID,
        "name": EXAMPLE_ORDERER_NAME,
        "phone": "01012345678",
        "phoneVerifiedAt": EXAMPLE_CREATED_AT,
        "createdAt": EXAMPLE_CREATED_AT,
        "lastLoginAt": EXAMPLE_UPDATED_AT,
        "alarmEnabled": False,
        "level": EXAMPLE_ORDERER_LEVEL,
    },
    "message": None,
}
USER_ALARM_EXAMPLE = {"success": True, "data": None, "message": "알람 설정이 업데이트되었습니다."}
USER_NAME_EXAMPLE = {"success": True, "data": None, "message": "닉네임이 업데이트되었습니다."}
USER_FCM_TOKEN_EXAMPLE = {"success": True, "data": None, "message": "FCM 토큰이 업데이트되었습니다."}
USER_WITHDRAWAL_REASONS_EXAMPLE = {
    "success": True,
    "data": [
        {
            "id": 1,
            "questionText": "원하는 임무가 많지 않았어요.",
            "displayOrder": 1,
            "requiresDetail": False,
        }
    ],
    "message": "Success",
}
USER_WITHDRAWAL_EXAMPLE = {
    "success": True,
    "data": {
        "id": 1,
        "userId": EXAMPLE_USER_ID,
        "reasonQuestionId": 1,
        "reasonQuestionText": "원하는 임무가 많지 않았어요.",
        "detailReason": "제 지역에는 요청이 거의 없었어요.",
        "withdrawnAt": EXAMPLE_CREATED_AT,
    },
    "message": "회원 탈퇴가 완료되었습니다.",
}

TERMS_AGREEMENT_EXAMPLE = {
    "success": True,
    "data": {
        "userId": EXAMPLE_USER_ID,
        "termsOfService": True,
        "privacyPolicy": True,
        "paymentRefundPolicy": True,
        "agreedAt": EXAMPLE_CREATED_AT,
    },
    "message": "약관 동의가 완료되었습니다.",
}

DISPUTE_SURVEY_QUESTIONS_EXAMPLE = {
    "success": True,
    "data": [
        {
            "id": 1,
            "targetType": "ORDER",
            "questionText": "러너의 수행 결과에 어떤 문제가 있었나요?",
            "displayOrder": 1,
            "requiresDetail": False,
        }
    ],
    "message": "Success",
}

PROPOSAL_EXAMPLE = {
    "id": 1,
    "title": "강남역 커피 배달",
    "content": "스타벅스 아메리카노 아이스 2잔 부탁드립니다.",
    "deadline": EXAMPLE_DEADLINE,
    "errandFee": 5000,
    "status": "POSTED",
}
PROPOSAL_STATE_TIMESTAMPS = {
    "ordererId": EXAMPLE_USER_ID,
    "ordererName": EXAMPLE_ORDERER_NAME,
    "ordererLevel": EXAMPLE_ORDERER_LEVEL,
    "matchedAt": None,
    "runnerConfirmedAt": None,
    "ordererConfirmedAt": None,
    "disputedAt": None,
    "resolvedAt": None,
    "openChatUrl": None,
    "offers": [],
}
PROPOSAL_WAITING_OFFER_EXAMPLE = {
    "id": 10,
    "proposalId": 1,
    "runnerId": EXAMPLE_RUNNER_ID,
    "runnerName": EXAMPLE_RUNNER_NAME,
    "runnerLevel": EXAMPLE_RUNNER_LEVEL,
    "status": "WAITING",
    "createdAt": EXAMPLE_CREATED_AT,
}
PROPOSAL_ACCEPTED_OFFER_EXAMPLE = {
    **PROPOSAL_WAITING_OFFER_EXAMPLE,
    "status": "ACCEPTED",
}
PROPOSAL_ALL_COMPLETED_OFFER_EXAMPLE = {
    **PROPOSAL_WAITING_OFFER_EXAMPLE,
    "status": "ALL_COMPLETED",
}
PROPOSAL_DISPUTED_OFFER_EXAMPLE = {
    **PROPOSAL_WAITING_OFFER_EXAMPLE,
    "status": "DISPUTED",
}
PROPOSAL_CANCELLED_OFFER_EXAMPLE = {
    **PROPOSAL_WAITING_OFFER_EXAMPLE,
    "status": "CANCELLED",
}
PROPOSAL_HOLDING_DETAIL_EXAMPLE = {
    **PROPOSAL_EXAMPLE,
    **PROPOSAL_STATE_TIMESTAMPS,
    "status": "HOLDING",
}
PROPOSAL_POSTED_DETAIL_EXAMPLE = {**PROPOSAL_EXAMPLE, **PROPOSAL_STATE_TIMESTAMPS}
PROPOSAL_DETAIL_EXAMPLE = PROPOSAL_POSTED_DETAIL_EXAMPLE
PROPOSAL_OFFERED_DETAIL_EXAMPLE = {
    **PROPOSAL_EXAMPLE,
    **PROPOSAL_STATE_TIMESTAMPS,
    "status": "OFFERED",
    "offers": [PROPOSAL_WAITING_OFFER_EXAMPLE],
}
PROPOSAL_MATCHED_DETAIL_EXAMPLE = {
    **PROPOSAL_EXAMPLE,
    **PROPOSAL_STATE_TIMESTAMPS,
    "status": "MATCHED",
    "matchedAt": EXAMPLE_UPDATED_AT,
    "openChatUrl": "https://open.kakao.com/o/example",
    "offers": [PROPOSAL_ACCEPTED_OFFER_EXAMPLE],
}
PROPOSAL_ORDER_COMPLETED_DETAIL_EXAMPLE = {
    **PROPOSAL_MATCHED_DETAIL_EXAMPLE,
    "status": "ORDER_COMPLETED",
    "ordererConfirmedAt": EXAMPLE_UPDATED_AT,
}
PROPOSAL_ALL_COMPLETED_DETAIL_EXAMPLE = {
    **PROPOSAL_MATCHED_DETAIL_EXAMPLE,
    "status": "ALL_COMPLETED",
    "runnerConfirmedAt": EXAMPLE_UPDATED_AT,
    "ordererConfirmedAt": EXAMPLE_UPDATED_AT,
    "offers": [PROPOSAL_ALL_COMPLETED_OFFER_EXAMPLE],
}
PROPOSAL_DISPUTED_DETAIL_EXAMPLE = {
    **PROPOSAL_MATCHED_DETAIL_EXAMPLE,
    "status": "DISPUTED",
    "disputedAt": EXAMPLE_UPDATED_AT,
    "offers": [PROPOSAL_DISPUTED_OFFER_EXAMPLE],
}
PROPOSAL_REFUND_PENDING_DETAIL_EXAMPLE = {
    **PROPOSAL_DISPUTED_DETAIL_EXAMPLE,
    "status": "REFUND_PENDING",
    "resolvedAt": EXAMPLE_UPDATED_AT,
    "offers": [PROPOSAL_CANCELLED_OFFER_EXAMPLE],
}
PROPOSAL_REFUNDED_DETAIL_EXAMPLE = {
    **PROPOSAL_REFUND_PENDING_DETAIL_EXAMPLE,
    "status": "REFUNDED",
}
PROPOSAL_CANCELLED_DETAIL_EXAMPLE = {
    **PROPOSAL_EXAMPLE,
    **PROPOSAL_STATE_TIMESTAMPS,
    "status": "CANCELLED",
    "offers": [PROPOSAL_CANCELLED_OFFER_EXAMPLE],
}
PROPOSAL_DETAIL_EXAMPLES = {
    "holding": {"success": True, "data": PROPOSAL_HOLDING_DETAIL_EXAMPLE, "message": None},
    "posted": {"success": True, "data": PROPOSAL_POSTED_DETAIL_EXAMPLE, "message": None},
    "offered": {"success": True, "data": PROPOSAL_OFFERED_DETAIL_EXAMPLE, "message": None},
    "matched": {"success": True, "data": PROPOSAL_MATCHED_DETAIL_EXAMPLE, "message": None},
    "order_completed": {"success": True, "data": PROPOSAL_ORDER_COMPLETED_DETAIL_EXAMPLE, "message": None},
    "all_completed": {"success": True, "data": PROPOSAL_ALL_COMPLETED_DETAIL_EXAMPLE, "message": None},
    "disputed": {"success": True, "data": PROPOSAL_DISPUTED_DETAIL_EXAMPLE, "message": None},
    "refund_pending": {"success": True, "data": PROPOSAL_REFUND_PENDING_DETAIL_EXAMPLE, "message": None},
    "refunded": {"success": True, "data": PROPOSAL_REFUNDED_DETAIL_EXAMPLE, "message": None},
    "cancelled": {"success": True, "data": PROPOSAL_CANCELLED_DETAIL_EXAMPLE, "message": None},
}
PROPOSAL_HOLDING_EXAMPLE = {**PROPOSAL_EXAMPLE, "status": "HOLDING"}
PROPOSAL_CANCELLED_EXAMPLE = {**PROPOSAL_EXAMPLE, "status": "CANCELLED"}
PROPOSAL_PAGE_EXAMPLE = {
    "success": True,
    "data": {
        "content": [PROPOSAL_EXAMPLE],
        "totalElements": 1,
        "totalPages": 1,
        "pageNumber": 0,
        "pageSize": 20,
        "first": True,
        "last": True,
    },
    "message": None,
}
PROPOSAL_OWN_EXAMPLE = {
    **PROPOSAL_EXAMPLE,
    "ordererId": EXAMPLE_USER_ID,
    "ordererName": EXAMPLE_ORDERER_NAME,
    "ordererLevel": EXAMPLE_ORDERER_LEVEL,
    "offerCount": 1,
    "offers": [
        {
            "id": 10,
            "proposalId": 1,
            "runnerId": EXAMPLE_RUNNER_ID,
            "runnerName": EXAMPLE_RUNNER_NAME,
            "runnerLevel": EXAMPLE_RUNNER_LEVEL,
            "status": "WAITING",
            "createdAt": EXAMPLE_CREATED_AT,
        }
    ],
    "createdAt": EXAMPLE_CREATED_AT,
    "updatedAt": EXAMPLE_UPDATED_AT,
}
PROPOSAL_OWN_PAGE_EXAMPLE = {
    "success": True,
    "data": {
        "content": [PROPOSAL_OWN_EXAMPLE],
        "totalElements": 1,
        "totalPages": 1,
        "pageNumber": 0,
        "pageSize": 20,
        "first": True,
        "last": True,
    },
    "message": None,
}
PROPOSAL_CREATE_EXAMPLE = {
    "success": True,
    "data": PROPOSAL_HOLDING_EXAMPLE,
    "message": "요청이 등록되었습니다.",
}
PROPOSAL_UPDATE_EXAMPLE = {
    "success": True,
    "data": {**PROPOSAL_HOLDING_EXAMPLE, "title": "수정된 제목"},
    "message": "요청이 수정되었습니다.",
}
PROPOSAL_CANCEL_EXAMPLE = {
    "success": True,
    "data": PROPOSAL_CANCELLED_EXAMPLE,
    "message": "요청이 취소되었습니다.",
}
PROPOSAL_RECEIVED_EXAMPLE = {
    "success": True,
    "data": PROPOSAL_ORDER_COMPLETED_DETAIL_EXAMPLE,
    "message": "완료 확인되었습니다.",
}
PROPOSAL_ALL_COMPLETED_RECEIVED_EXAMPLE = {
    "success": True,
    "data": PROPOSAL_ALL_COMPLETED_DETAIL_EXAMPLE,
    "message": "완료 확인되었습니다.",
}
PROPOSAL_DISPUTE_EXAMPLE = {
    "success": True,
    "data": PROPOSAL_DISPUTED_DETAIL_EXAMPLE,
    "message": "분쟁이 접수되었습니다.",
}
DISPUTE_EVIDENCE_EXAMPLE = {
    "success": True,
    "data": {
        "id": 1,
        "proposalId": 1,
        "offerId": 10,
        "actorId": EXAMPLE_RUNNER_ID,
        "reasonQuestionId": 3,
        "reasonQuestionText": "물건이 파손되었어요",
        "detailReason": "배송 중 파손",
        "createdAt": EXAMPLE_CREATED_AT,
    },
    "message": "Success",
}

OFFER_EXAMPLE = {
    "id": 10,
    "proposalId": 1,
    "ordererId": EXAMPLE_USER_ID,
    "ordererName": EXAMPLE_ORDERER_NAME,
    "ordererLevel": EXAMPLE_ORDERER_LEVEL,
    "runnerId": EXAMPLE_RUNNER_ID,
    "runnerName": EXAMPLE_RUNNER_NAME,
    "runnerLevel": EXAMPLE_RUNNER_LEVEL,
    "status": "WAITING",
    "acceptedAt": None,
    "runnerConfirmedAt": None,
    "ordererConfirmedAt": None,
    "disputedAt": None,
    "resolvedAt": None,
    "createdAt": EXAMPLE_CREATED_AT,
}
OFFER_WAITING_EXAMPLE = OFFER_EXAMPLE
OFFER_ACCEPTED_EXAMPLE = {**OFFER_EXAMPLE, "status": "ACCEPTED", "acceptedAt": EXAMPLE_UPDATED_AT}
OFFER_RUNNER_COMPLETED_EXAMPLE = {
    **OFFER_EXAMPLE,
    "status": "RUNNER_COMPLETED",
    "acceptedAt": EXAMPLE_CREATED_AT,
    "runnerConfirmedAt": EXAMPLE_UPDATED_AT,
}
OFFER_ALL_COMPLETED_EXAMPLE = {
    **OFFER_RUNNER_COMPLETED_EXAMPLE,
    "status": "ALL_COMPLETED",
    "ordererConfirmedAt": EXAMPLE_UPDATED_AT,
}
OFFER_DISPUTED_STATUS_EXAMPLE = {
    **OFFER_EXAMPLE,
    "status": "DISPUTED",
    "acceptedAt": EXAMPLE_CREATED_AT,
    "disputedAt": EXAMPLE_UPDATED_AT,
}
OFFER_REJECTED_EXAMPLE = {**OFFER_EXAMPLE, "status": "REJECTED"}
OFFER_CANCELLED_EXAMPLE = {**OFFER_EXAMPLE, "status": "CANCELLED"}
OFFER_STATUS_DATA_EXAMPLES = {
    "waiting": OFFER_WAITING_EXAMPLE,
    "accepted": OFFER_ACCEPTED_EXAMPLE,
    "runner_completed": OFFER_RUNNER_COMPLETED_EXAMPLE,
    "all_completed": OFFER_ALL_COMPLETED_EXAMPLE,
    "disputed": OFFER_DISPUTED_STATUS_EXAMPLE,
    "rejected": OFFER_REJECTED_EXAMPLE,
    "cancelled": OFFER_CANCELLED_EXAMPLE,
}
OFFER_OPEN_CHAT_EXAMPLE = "https://open.kakao.com/o/example"
OFFER_OPEN_CHAT_EXAMPLE_STATUSES = {
    "accepted",
    "runner_completed",
    "all_completed",
    "disputed",
}
OFFER_DETAIL_EXAMPLES = {
    name: {
        "success": True,
        "data": {
            **data,
            "openChatUrl": OFFER_OPEN_CHAT_EXAMPLE if name in OFFER_OPEN_CHAT_EXAMPLE_STATUSES else None,
        },
        "message": "Success",
    }
    for name, data in OFFER_STATUS_DATA_EXAMPLES.items()
}
OFFER_LIST_EXAMPLES = {
    name: {"success": True, "data": [data], "message": "Success"}
    for name, data in OFFER_STATUS_DATA_EXAMPLES.items()
}
OFFER_PAGE_EXAMPLES = {
    name: {
        "success": True,
        "data": {
            "content": [data],
            "totalElements": 1,
            "totalPages": 1,
            "pageNumber": 0,
            "pageSize": 20,
            "first": True,
            "last": True,
        },
        "message": "Success",
    }
    for name, data in OFFER_STATUS_DATA_EXAMPLES.items()
}
OFFER_PAGE_EXAMPLE = {
    "success": True,
    "data": {
        "content": [OFFER_EXAMPLE],
        "totalElements": 1,
        "totalPages": 1,
        "pageNumber": 0,
        "pageSize": 20,
        "first": True,
        "last": True,
    },
    "message": "Success",
}
OFFER_LIST_EXAMPLE = {"success": True, "data": [OFFER_EXAMPLE], "message": "Success"}
OFFER_CREATE_EXAMPLE = {"success": True, "data": OFFER_EXAMPLE, "message": "지원이 접수되었습니다."}
OFFER_DETAIL_EXAMPLE = {"success": True, "data": OFFER_EXAMPLE, "message": "Success"}
OFFER_ACCEPTED_DETAIL_EXAMPLE = OFFER_DETAIL_EXAMPLES["accepted"]
OFFER_COMPLETE_DELIVERY_EXAMPLES = {
    "runner_completed": {
        "success": True,
        "data": OFFER_RUNNER_COMPLETED_EXAMPLE,
        "message": "완료 처리되었습니다.",
    },
    "all_completed": {
        "success": True,
        "data": OFFER_ALL_COMPLETED_EXAMPLE,
        "message": "완료 처리되었습니다.",
    },
}
OFFER_DISPUTE_EXAMPLE = {
    "success": True,
    "data": OFFER_DISPUTED_STATUS_EXAMPLE,
    "message": "분쟁이 접수되었습니다.",
}
OFFER_ACCEPT_EXAMPLE = {
    "success": True,
    "data": {
        "proposalId": 1,
        "offerId": 10,
        "proposalStatus": "MATCHED",
        "acceptedOfferStatus": "ACCEPTED",
        "rejectedOfferCount": 1,
        "ordererId": EXAMPLE_USER_ID,
        "ordererName": EXAMPLE_ORDERER_NAME,
        "ordererLevel": EXAMPLE_ORDERER_LEVEL,
        "runnerId": EXAMPLE_RUNNER_ID,
        "runnerName": EXAMPLE_RUNNER_NAME,
        "runnerLevel": EXAMPLE_RUNNER_LEVEL,
        "acceptedAt": EXAMPLE_CREATED_AT,
    },
    "message": "지원이 수락되었습니다.",
}

EXAMPLE_MISSION_ID = 1
MISSION_EXAMPLE = {
    "id": EXAMPLE_MISSION_ID,
    "proposalId": 1,
    "offerId": 10,
    "ordererId": EXAMPLE_USER_ID,
    "ordererName": EXAMPLE_ORDERER_NAME,
    "runnerId": EXAMPLE_RUNNER_ID,
    "runnerName": EXAMPLE_RUNNER_NAME,
    "openChatUrl": OFFER_OPEN_CHAT_EXAMPLE,
    "status": "STARTED",
    "errandFee": 15000,
    "settlementPaid": False,
    "settlementStatus": "PENDING",
    "resolution": None,
    "startedAt": EXAMPLE_CREATED_AT,
    "runnerConfirmedAt": None,
    "ordererConfirmedAt": None,
    "disputedAt": None,
    "completedAt": None,
    "failedAt": None,
    "resolvedAt": None,
    "resolvedByAdminId": None,
    "settlementPaidAt": None,
    "settlementPaidByAdminId": None,
    "payoutMemo": None,
    "createdAt": EXAMPLE_CREATED_AT,
}


def _mission_example(**overrides: Any) -> dict[str, Any]:
    return {**MISSION_EXAMPLE, **overrides}


MISSION_STATUS_EXAMPLES = {
    "started": _mission_example(),
    "disputed": _mission_example(status="DISPUTED", disputedAt=EXAMPLE_UPDATED_AT),
    "completed": _mission_example(
        status="COMPLETED",
        runnerConfirmedAt=EXAMPLE_CREATED_AT,
        ordererConfirmedAt=EXAMPLE_UPDATED_AT,
        completedAt=EXAMPLE_UPDATED_AT,
    ),
    "paid": _mission_example(
        status="PAID",
        settlementStatus="COMPLETED",
        runnerConfirmedAt=EXAMPLE_CREATED_AT,
        ordererConfirmedAt=EXAMPLE_UPDATED_AT,
        completedAt=EXAMPLE_UPDATED_AT,
        settlementPaid=True,
        settlementPaidAt=EXAMPLE_UPDATED_AT,
        settlementPaidByAdminId=EXAMPLE_USER_ID,
        payoutMemo="이체 참조번호 20260601-001",
    ),
    "failed": _mission_example(
        status="FAILED",
        disputedAt=EXAMPLE_CREATED_AT,
        failedAt=EXAMPLE_UPDATED_AT,
        resolution="FAILED",
        resolvedAt=EXAMPLE_UPDATED_AT,
        resolvedByAdminId=EXAMPLE_USER_ID,
    ),
}

MISSION_DETAIL_EXAMPLES = {
    name: {"success": True, "data": example, "message": None}
    for name, example in MISSION_STATUS_EXAMPLES.items()
}
MISSION_PAGE_EXAMPLES = {
    name: {
        "success": True,
        "data": {
            "content": [example],
            "totalElements": 1,
            "totalPages": 1,
            "pageNumber": 0,
            "pageSize": 20,
            "first": True,
            "last": True,
        },
        "message": None,
    }
    for name, example in MISSION_STATUS_EXAMPLES.items()
}
MISSION_RESOLVED_EXAMPLES = {
    "completed": {
        "success": True,
        "data": _mission_example(
            status="COMPLETED",
            disputedAt=EXAMPLE_CREATED_AT,
            completedAt=EXAMPLE_UPDATED_AT,
            resolution="COMPLETED",
            resolvedAt=EXAMPLE_UPDATED_AT,
            resolvedByAdminId=EXAMPLE_USER_ID,
        ),
        "message": "미션 분쟁이 해결되었습니다.",
    },
    "failed": {
        "success": True,
        "data": MISSION_STATUS_EXAMPLES["failed"],
        "message": "미션 분쟁이 해결되었습니다.",
    },
}
MISSION_SETTLEMENT_EXAMPLE = {
    "success": True,
    "data": MISSION_STATUS_EXAMPLES["paid"],
    "message": "수행비 지급을 기록했습니다.",
}
SETTLEMENT_ACCOUNT_EXAMPLE = {
    "bankName": "국민은행",
    "accountHolder": "홍길동",
    "maskedAccountNumber": "********9012",
    "updatedAt": EXAMPLE_UPDATED_AT,
}
SETTLEMENT_ACCOUNT_GET_EXAMPLE = {"success": True, "data": SETTLEMENT_ACCOUNT_EXAMPLE, "message": "Success"}
SETTLEMENT_ACCOUNT_EMPTY_EXAMPLE = {"success": True, "data": None, "message": "Success"}
SETTLEMENT_ACCOUNT_SAVE_EXAMPLE = {
    "success": True,
    "data": SETTLEMENT_ACCOUNT_EXAMPLE,
    "message": "정산 계좌가 저장되었습니다.",
}

NOTIFICATION_EXAMPLE = {
    "id": 1,
    "user_id": EXAMPLE_USER_ID,
    "notification_type": "custom",
    "title": "테스트 알림",
    "body": "테스트 알림 본문입니다.",
    "data": "{\"proposalId\":\"1\"}",
    "related_entity_type": "proposal",
    "related_entity_id": 1,
    "status": "sent",
    "fcm_message_id": "projects/orderrun/messages/1",
    "error_message": "No FCM token",
    "created_at": EXAMPLE_CREATED_AT,
    "sent_at": EXAMPLE_CREATED_AT,
    "delivered_at": EXAMPLE_UPDATED_AT,
    "read_at": EXAMPLE_UPDATED_AT,
}
NOTIFICATION_LIST_EXAMPLE = {
    "success": True,
    "data": {
        "total": 1,
        "notifications": [NOTIFICATION_EXAMPLE],
        "page": 1,
        "page_size": 20,
    },
    "message": "Success",
}
NOTIFICATION_STATS_EXAMPLE = {
    "success": True,
    "data": {
        "total_notifications": 3,
        "unread_count": 1,
        "failed_count": 1,
        "read_count": 2,
    },
    "message": "Success",
}
NOTIFICATION_MARK_READ_EXAMPLE = {
    "success": True,
    "data": {"marked_count": 1},
    "message": "1 notification(s) marked as read",
}
NOTIFICATION_RESPONSE_EXAMPLE = {"success": True, "data": NOTIFICATION_EXAMPLE, "message": "Success"}

ROOT_EXAMPLE = {"message": "Welcome to OrderRun API", "version": "0.1.0", "docs": "/docs"}
HEALTH_EXAMPLE = {"success": True, "data": {"status": "UP"}, "message": "Success"}


# ---------------------------------------------------------------- 관리자 웹

def _admin_page(example: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "content": [example],
            "totalElements": 1,
            "totalPages": 1,
            "pageNumber": 0,
            "pageSize": 20,
            "first": True,
            "last": True,
        },
        "message": None,
    }


ADMIN_PROPOSAL_SUMMARY_EXAMPLE = {
    "id": 1,
    "ordererId": EXAMPLE_USER_ID,
    "ordererName": EXAMPLE_ORDERER_NAME,
    "errandFee": 5000,
    "status": "POSTED",
    "offerCount": 1,
    "createdAt": EXAMPLE_CREATED_AT,
}
ADMIN_PROPOSAL_PAGE_EXAMPLE = _admin_page(ADMIN_PROPOSAL_SUMMARY_EXAMPLE)
ADMIN_PROPOSAL_DETAIL_EXAMPLE = {
    "id": 1,
    "title": "강남역 커피 배달",
    "content": "스타벅스 아메리카노 아이스 2잔 부탁드립니다.",
    "deadline": EXAMPLE_DEADLINE,
    "errandFee": 5000,
    "ordererId": EXAMPLE_USER_ID,
    "ordererName": EXAMPLE_ORDERER_NAME,
    "ordererLevel": EXAMPLE_ORDERER_LEVEL,
    "status": "MATCHED",
    "createdAt": EXAMPLE_CREATED_AT,
    "openChatUrl": "https://open.kakao.com/o/example",
    "acceptedOfferId": 10,
    "acceptedRunnerName": EXAMPLE_RUNNER_NAME,
    "missionId": 100,
    "adminNote": None,
    "depositorName": None,
    "depositBankName": "국민은행",
    "depositAccountNumber": "123456789012",
    "depositAccountHolder": "오더런",
    "matchedAt": EXAMPLE_UPDATED_AT,
    "runnerConfirmedAt": None,
    "ordererConfirmedAt": None,
    "disputedAt": None,
    "resolvedAt": None,
}
ADMIN_PROPOSAL_DETAIL_RESPONSE_EXAMPLE = {
    "success": True,
    "data": ADMIN_PROPOSAL_DETAIL_EXAMPLE,
    "message": None,
}
ADMIN_PROPOSAL_CANCELLED_EXAMPLE = {
    "success": True,
    "data": {**ADMIN_PROPOSAL_DETAIL_EXAMPLE, "status": "CANCELLED", "adminNote": "행님 요청으로 취소"},
    "message": "요청이 취소되었습니다.",
}

ADMIN_OFFER_SUMMARY_EXAMPLE = {
    "id": 10,
    "proposalId": 1,
    "runnerId": EXAMPLE_RUNNER_ID,
    "runnerName": EXAMPLE_RUNNER_NAME,
    "runnerLevel": EXAMPLE_RUNNER_LEVEL,
    "status": "ACCEPTED",
    "accepted": True,
    "hasDispute": False,
    "amount": 5000,
    "openChatUrl": "https://open.kakao.com/o/example",
    "createdAt": EXAMPLE_CREATED_AT,
}
ADMIN_OFFER_PAGE_EXAMPLE = _admin_page(ADMIN_OFFER_SUMMARY_EXAMPLE)

PROPOSAL_REPORT_EXAMPLE = {
    "id": 1,
    "proposalId": 1,
    "reporterId": EXAMPLE_RUNNER_ID,
    "reporterName": EXAMPLE_RUNNER_NAME,
    "reasonQuestionId": 1,
    "reasonQuestionText": "광고 또는 스팸이에요",
    "detailReason": "같은 글을 반복해서 올려요.",
    "status": "PENDING",
    "createdAt": EXAMPLE_CREATED_AT,
    "reviewedAt": None,
    "proposalStatus": "POSTED",
}


def _report_example(**overrides: Any) -> dict[str, Any]:
    return {**PROPOSAL_REPORT_EXAMPLE, **overrides}


#: 미검토·검토 완료 두 가지를 함께 노출한다. OpenAPI 인코딩이 null 필드를 예시에서 지우기 때문에
#: 한 예시만 두면 reviewedAt 같은 필드가 문서에서 사라진다.
PROPOSAL_REPORT_PAGE_EXAMPLES = {
    "pending": _admin_page(PROPOSAL_REPORT_EXAMPLE),
    "reviewed": _admin_page(
        _report_example(
            id=2,
            status="ACCEPTED",
            reviewedAt=EXAMPLE_UPDATED_AT,
            proposalStatus="REPORTED",
        )
    ),
}


def _reviewed_report_example(status: str, message: str) -> dict[str, Any]:
    """승인·반려 응답 예시. 단건 조회라 proposalStatus는 채우지 않는다."""
    return {
        "success": True,
        "data": _report_example(status=status, reviewedAt=EXAMPLE_UPDATED_AT, proposalStatus=None),
        "message": message,
    }


PROPOSAL_REPORT_ACCEPTED_EXAMPLE = _reviewed_report_example("ACCEPTED", "신고가 승인되었습니다.")
PROPOSAL_REPORT_REJECTED_EXAMPLE = _reviewed_report_example("REJECTED", "신고가 반려되었습니다.")

ADMIN_DISPUTE_SUMMARY_EXAMPLE = {
    "id": 5,
    "proposalId": 1,
    "offerId": 10,
    "missionId": 100,
    "requesterId": EXAMPLE_USER_ID,
    "requesterName": EXAMPLE_ORDERER_NAME,
    "requesterRole": "ORDERER",
    "status": "PENDING",
    "createdAt": EXAMPLE_CREATED_AT,
}
ADMIN_DISPUTE_PAGE_EXAMPLE = _admin_page(ADMIN_DISPUTE_SUMMARY_EXAMPLE)
ADMIN_DISPUTE_DETAIL_EXAMPLE = {
    **ADMIN_DISPUTE_SUMMARY_EXAMPLE,
    "targetId": EXAMPLE_RUNNER_ID,
    "targetName": EXAMPLE_RUNNER_NAME,
    "targetRole": "RUNNER",
    "reasonQuestionId": 1,
    "reasonQuestionText": "물건이 파손되었어요",
    "detailReason": "약속한 물건과 다른 물건을 전달했습니다.",
    "proposalStatus": "DISPUTED",
    "offerStatus": "DISPUTED",
    "adminNote": None,
    "resolvedAt": None,
}
ADMIN_DISPUTE_DETAIL_RESPONSE_EXAMPLE = {
    "success": True,
    "data": ADMIN_DISPUTE_DETAIL_EXAMPLE,
    "message": None,
}
ADMIN_DISPUTE_RESOLVED_EXAMPLE = {
    "success": True,
    "data": {
        **ADMIN_DISPUTE_DETAIL_EXAMPLE,
        "status": "RESOLVED",
        "proposalStatus": "ALL_COMPLETED",
        "offerStatus": "ALL_COMPLETED",
        "adminNote": "꼬붕 과실 확인",
        "resolvedAt": EXAMPLE_UPDATED_AT,
    },
    "message": "분쟁이 처리되었습니다.",
}
ADMIN_REFUND_SUMMARY_EXAMPLE = {
    "id": 100,
    "proposalId": 1,
    "proposalStatus": "REFUND_PENDING",
    "ordererId": EXAMPLE_USER_ID,
    "ordererName": EXAMPLE_ORDERER_NAME,
    "amount": 5000,
    "status": "PENDING",
    "reason": "DISPUTE_FAILED",
    "requestedAt": EXAMPLE_UPDATED_AT,
    "processedAt": None,
}
ADMIN_REFUND_PAGE_EXAMPLE = _admin_page(ADMIN_REFUND_SUMMARY_EXAMPLE)
ADMIN_REFUND_DETAIL_EXAMPLE = {
    **ADMIN_REFUND_SUMMARY_EXAMPLE,
    "reasonDetail": "약속한 물건과 다른 물건을 전달했습니다.",
    "refundBankName": "국민은행",
    "refundAccountNumber": "123456789012",
    "refundAccountHolder": EXAMPLE_ORDERER_NAME,
    "adminNote": None,
}
ADMIN_REFUND_DETAIL_RESPONSE_EXAMPLE = {
    "success": True,
    "data": ADMIN_REFUND_DETAIL_EXAMPLE,
    "message": None,
}
ADMIN_REFUND_COMPLETED_EXAMPLE = {
    "success": True,
    "data": {
        **ADMIN_REFUND_DETAIL_EXAMPLE,
        "proposalStatus": "REFUNDED",
        "status": "COMPLETED",
        "processedAt": EXAMPLE_UPDATED_AT,
        "adminNote": "이체 참조번호 20260601-002",
    },
    "message": "환불을 기록했습니다.",
}
ADMIN_REFUND_DEPOSIT_CONFIRMED_EXAMPLE = {
    "success": True,
    "data": {
        **ADMIN_REFUND_DETAIL_EXAMPLE,
        "proposalStatus": "REFUND_PENDING",
        "status": "PENDING",
        "reason": "USER_CANCELLED",
        "reasonDetail": None,
    },
    "message": "입금이 확인되어 환불 대상으로 확정했습니다.",
}
ADMIN_REFUND_VOIDED_EXAMPLE = {
    "success": True,
    "data": {
        **ADMIN_REFUND_DETAIL_EXAMPLE,
        "proposalStatus": "CANCELLED",
        "status": "VOIDED",
        "reason": "PAYMENT_EXPIRED",
        "reasonDetail": None,
        "processedAt": EXAMPLE_UPDATED_AT,
        "adminNote": "2026-06-01 입금 내역 없음",
    },
    "message": "입금이 없어 환불 없이 종결했습니다.",
}
ADMIN_PAYOUT_PAGE_EXAMPLE = _admin_page(
    _mission_example(
        status="COMPLETED",
        completedAt=EXAMPLE_UPDATED_AT,
        settlementStatus="PENDING",
    )
)
ADMIN_PAYOUT_DETAIL_BASE_EXAMPLE = {
    "id": 100,
    "proposalId": 1,
    "offerId": 10,
    "runnerId": EXAMPLE_RUNNER_ID,
    "runnerName": EXAMPLE_RUNNER_NAME,
    "amount": 5000,
    "status": "PENDING",
    "settledAt": None,
}
ADMIN_PAYOUT_DETAIL_EXAMPLE = {
    **ADMIN_PAYOUT_DETAIL_BASE_EXAMPLE,
    "payoutBankName": "국민은행",
    "payoutAccountNumber": "123456789012",
    "payoutAccountHolder": EXAMPLE_RUNNER_NAME,
    "adminNote": None,
}
ADMIN_PAYOUT_DETAIL_RESPONSE_EXAMPLE = {
    "success": True,
    "data": ADMIN_PAYOUT_DETAIL_EXAMPLE,
    "message": None,
}
ADMIN_PAYOUT_COMPLETED_EXAMPLE = {
    "success": True,
    "data": {
        **ADMIN_PAYOUT_DETAIL_EXAMPLE,
        "status": "COMPLETED",
        "settledAt": EXAMPLE_UPDATED_AT,
        "adminNote": "이체 참조번호 20260601-001",
    },
    "message": "수행비 지급을 기록했습니다.",
}
ADMIN_PAYOUT_REJECTED_EXAMPLE = {
    "success": True,
    "data": {
        **ADMIN_PAYOUT_DETAIL_EXAMPLE,
        "status": "REJECTED",
        "settledAt": EXAMPLE_UPDATED_AT,
        "adminNote": "정산 계좌 미등록",
    },
    "message": "수행비 지급을 반려했습니다.",
}

ADMIN_USER_SUMMARY_EXAMPLE = {
    "id": EXAMPLE_USER_ID,
    "name": EXAMPLE_ORDERER_NAME,
    "createdAt": EXAMPLE_CREATED_AT,
    "missionCount": EXAMPLE_RUNNER_LEVEL,
}
ADMIN_USER_PAGE_EXAMPLE = _admin_page(ADMIN_USER_SUMMARY_EXAMPLE)
ADMIN_SUMMARY_EXAMPLE = {
    "success": True,
    "data": {
        "unpaidCount": 3,
        "disputeCount": 1,
        "refundCount": 0,
        "depositReviewCount": 2,
        "settlementCount": 2,
        "reportCount": 1,
    },
    "message": None,
}

ADMIN_LOGIN_EXAMPLE = {
    "success": True,
    "data": {
        "accessToken": "access-token",
        "refreshToken": "refresh-token",
        "tokenType": "Bearer",
        "expiresIn": 3600000,
        "userId": EXAMPLE_USER_ID,
    },
    "message": None,
}
