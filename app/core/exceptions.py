"""Exception handlers that wrap every failure in the standard response envelope."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.errors import AppError, ErrorCode, error_detail

logger = logging.getLogger(__name__)


# Starlette가 직접 발생시키는 HTTPException(라우트 404, 405)은 detail이 문자열이므로
# 카탈로그 항목으로 대체해 클라이언트가 분기할 수 있는 code를 부여한다.
# 카탈로그 밖의 HTTPException이 봉투를 탈 때 쓰는 문구. 정상 경로에서는 쓰이지 않는다.
HTTP_ERROR_MESSAGE = "요청을 처리할 수 없습니다."

_STATUS_FALLBACK: dict[int, AppError] = {
    status.HTTP_404_NOT_FOUND: AppError.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: AppError.METHOD_NOT_ALLOWED,
}


def _envelope(status_code: int, error: dict) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


def _fallback_error(status_code: int, detail: object) -> dict:
    """Build an error body for exceptions raised outside the AppError catalog."""
    mapped = _STATUS_FALLBACK.get(status_code)
    if mapped is not None:
        return error_detail(mapped)
    if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        return error_detail(AppError.INTERNAL_SERVER_ERROR)
    # 열거형 밖의 코드는 내보내지 않는다. ErrorDetail.code가 ErrorCode로 고정돼 있어
    # 스키마가 약속한 값 집합을 응답이 어기면 안 된다.
    # 원본 detail은 라이브러리가 만든 영문 문자열이라 사용자에게 노출하지 않고,
    # 디버그 환경에서만 details로 넘긴다.
    return {
        "code": ErrorCode.HTTP_ERROR.value,
        "message": HTTP_ERROR_MESSAGE,
        "details": str(detail) if settings.app_debug else None,
    }


async def http_exception_handler(request: Request, exc: Exception):
    """Handle both FastAPI and Starlette HTTPException in the standard envelope."""
    _ = request

    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        error = exc.detail if isinstance(exc.detail, dict) else _fallback_error(exc.status_code, exc.detail)
        return _envelope(exc.status_code, error)

    return await unhandled_exception_handler(request, exc)


async def unhandled_exception_handler(request: Request, exc: Exception):
    """Wrap unhandled exceptions so no response ever escapes the envelope."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)

    # 예외 문자열은 내부 정보를 노출할 수 있으므로 디버그 모드에서만 담는다.
    details = str(exc) if settings.app_debug else None
    return _envelope(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_detail(AppError.INTERNAL_SERVER_ERROR, details),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors and return custom error response."""
    _ = request

    errors = exc.errors()
    if errors:
        first_error = errors[0]
        field = first_error["loc"][-1] if first_error["loc"] else "unknown"
        message = first_error["msg"]
        details = f"{field}: {message}"
    else:
        first_error = None
        field = "unknown"
        details = "Validation error"

    error = AppError.VALIDATION_ERROR
    if field == "deadline" and first_error and first_error.get("type") in {
        "datetime_from_date_parsing",
        "datetime_parsing",
        "invalid_datetime_offset",
    }:
        error = AppError.INVALID_DATE_TIME_FORMAT

    return _envelope(status.HTTP_400_BAD_REQUEST, error_detail(error, details))
