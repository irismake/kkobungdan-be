from __future__ import annotations

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.errors import ERRORS, AppError, ErrorCode, api_error, error_detail
from app.core.exceptions import http_exception_handler, unhandled_exception_handler


def test_error_catalog_has_required_fields_for_every_error():
    assert set(ERRORS) == set(AppError)
    for spec in ERRORS.values():
        assert spec.http_status >= 400
        assert spec.code
        assert spec.message


def test_api_error_builds_standard_http_exception_detail():
    exc = api_error(AppError.SMS_SENDER_NOT_CONFIGURED)

    assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert exc.detail == {
        "code": "SMS_SENDER_NOT_CONFIGURED",
        "message": "SMS 발신 설정이 완료되지 않았습니다.",
        "details": None,
    }


def test_api_error_preserves_details_and_headers():
    exc = api_error(
        AppError.INVALID_TOKEN_CREDENTIALS,
        details="token: invalid signature",
        headers={"WWW-Authenticate": "Bearer"},
    )

    assert exc.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc.headers == {"WWW-Authenticate": "Bearer"}
    assert exc.detail == {
        "code": "INVALID_TOKEN",
        "message": "인증 정보를 확인할 수 없습니다.",
        "details": "token: invalid signature",
    }


def test_error_detail_uses_validation_catalog_message():
    assert error_detail(AppError.VALIDATION_ERROR, "field: error") == {
        "code": "VALIDATION_ERROR",
        "message": "요청 값이 올바르지 않습니다.",
        "details": "field: error",
    }


def test_every_catalog_message_is_korean():
    for error, spec in ERRORS.items():
        assert any("가" <= char <= "힣" for char in spec.message), f"{error.name} 메시지가 한국어가 아니다"


def _envelope_app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/boom")
    def boom():
        raise RuntimeError("internal detail leaked")

    @app.get("/ok")
    def ok():
        return {"ok": True}

    return app


def _assert_envelope(payload: dict, code: str) -> None:
    assert payload["success"] is False
    assert set(payload["error"]) == {"code", "message", "details"}
    assert payload["error"]["code"] == code
    assert payload["error"]["message"]
    assert payload["timestamp"]


def test_unknown_route_returns_envelope():
    client = TestClient(_envelope_app())

    response = client.get("/no-such-route")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    _assert_envelope(response.json(), "NOT_FOUND")


def test_method_not_allowed_returns_envelope():
    client = TestClient(_envelope_app())

    response = client.post("/ok")

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    _assert_envelope(response.json(), "METHOD_NOT_ALLOWED")


def test_unhandled_exception_returns_envelope_without_leaking_details():
    client = TestClient(_envelope_app(), raise_server_exceptions=False)
    original_debug = settings.app_debug
    settings.app_debug = False
    try:
        response = client.get("/boom")
    finally:
        settings.app_debug = original_debug

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    _assert_envelope(response.json(), "INTERNAL_SERVER_ERROR")
    assert response.json()["error"]["details"] is None
    assert "internal detail leaked" not in response.text


def test_unhandled_exception_includes_details_in_debug_mode():
    client = TestClient(_envelope_app(), raise_server_exceptions=False)
    original_debug = settings.app_debug
    settings.app_debug = True
    try:
        response = client.get("/boom")
    finally:
        settings.app_debug = original_debug

    assert response.json()["error"]["details"] == "internal detail leaked"


def test_error_code_enum_matches_catalog():
    """ErrorCode는 카탈로그가 내보내는 코드 + 방어용 HTTP_ERROR로만 구성된다."""
    catalog_codes = {spec.code for spec in ERRORS.values()}

    assert catalog_codes | {ErrorCode.HTTP_ERROR} == set(ErrorCode)


def test_catalog_codes_are_error_code_members():
    """문자열 리터럴이 섞여 스키마 열거형을 벗어나지 않도록 고정한다."""
    for error, spec in ERRORS.items():
        assert isinstance(spec.code, ErrorCode), f"{error.name}의 code가 ErrorCode가 아니다"


def test_fallback_error_stays_inside_error_code_enum():
    from app.core.exceptions import _fallback_error

    body = _fallback_error(418, "I'm a teapot")

    assert body["code"] == ErrorCode.HTTP_ERROR.value
    assert ErrorCode(body["code"]) in ErrorCode


def test_no_raw_http_exception_is_raised_in_app_code():
    """HTTP_ERROR는 api_error를 우회해 raw HTTPException을 던질 때만 발생한다.

    카탈로그를 거치지 않는 에러가 생기면 코드도 문구도 계약을 벗어나므로,
    발생 원인 자체를 막는다.
    """
    import re
    from pathlib import Path

    offenders = []
    for path in Path("app").rglob("*.py"):
        if path.name in {"errors.py", "exceptions.py"}:
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"\braise HTTPException\(", line):
                offenders.append(f"{path}:{lineno}")

    assert not offenders, (
        "raw HTTPException 대신 app.core.errors.api_error()를 사용한다: " + ", ".join(offenders)
    )


def test_fallback_error_does_not_leak_upstream_message():
    from app.core.config import settings
    from app.core.exceptions import HTTP_ERROR_MESSAGE, _fallback_error

    original = settings.app_debug
    settings.app_debug = False
    try:
        body = _fallback_error(409, "conflict as plain string")
    finally:
        settings.app_debug = original

    assert body["message"] == HTTP_ERROR_MESSAGE
    assert body["details"] is None
