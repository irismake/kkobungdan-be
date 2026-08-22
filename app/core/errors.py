"""Central API error catalog and HTTPException factory."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fastapi import HTTPException, status


class ErrorCode(str, Enum):
    """클라이언트에 실제로 나가는 wire code. `error.code`의 유일한 값 집합이다."""

    DISPUTE_EVIDENCE_NOT_FOUND = "DISPUTE_EVIDENCE_NOT_FOUND"
    DUPLICATE_OFFER = "DUPLICATE_OFFER"
    DUPLICATE_PROPOSAL_REPORT = "DUPLICATE_PROPOSAL_REPORT"
    FORBIDDEN = "FORBIDDEN"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    INVALID_DATE_TIME_FORMAT = "INVALID_DATE_TIME_FORMAT"
    INVALID_STATUS = "INVALID_STATUS"
    INVALID_TOKEN = "INVALID_TOKEN"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    NOTIFICATION_NOT_FOUND = "NOTIFICATION_NOT_FOUND"
    NOT_FOUND = "NOT_FOUND"
    OFFER_NOT_ACCEPTABLE = "OFFER_NOT_ACCEPTABLE"
    OFFER_NOT_CANCELLABLE = "OFFER_NOT_CANCELLABLE"
    OFFER_NOT_FOUND = "OFFER_NOT_FOUND"
    OFFER_NOT_UPDATABLE = "OFFER_NOT_UPDATABLE"
    PHONE_ALREADY_EXISTS = "PHONE_ALREADY_EXISTS"
    PHONE_VERIFICATION_CODE_MISMATCH = "PHONE_VERIFICATION_CODE_MISMATCH"
    PHONE_VERIFICATION_EXPIRED = "PHONE_VERIFICATION_EXPIRED"
    PHONE_VERIFICATION_NOT_FOUND = "PHONE_VERIFICATION_NOT_FOUND"
    PHONE_VERIFICATION_SEND_RATE_LIMITED = "PHONE_VERIFICATION_SEND_RATE_LIMITED"
    PROPOSAL_DEADLINE_INVALID = "PROPOSAL_DEADLINE_INVALID"
    PROPOSAL_ERRAND_FEE_INVALID = "PROPOSAL_ERRAND_FEE_INVALID"
    PROPOSAL_NOT_CANCELLABLE = "PROPOSAL_NOT_CANCELLABLE"
    PROPOSAL_NOT_EDITABLE = "PROPOSAL_NOT_EDITABLE"
    PROPOSAL_NOT_FOUND = "PROPOSAL_NOT_FOUND"
    PROPOSAL_NOT_MATCHABLE = "PROPOSAL_NOT_MATCHABLE"
    PROPOSAL_NOT_OPEN = "PROPOSAL_NOT_OPEN"
    PROPOSAL_NOT_REPORTABLE = "PROPOSAL_NOT_REPORTABLE"
    PROPOSAL_NOT_UPDATABLE = "PROPOSAL_NOT_UPDATABLE"
    PROPOSAL_REPORT_NOT_FOUND = "PROPOSAL_REPORT_NOT_FOUND"
    PROPOSAL_REPORT_NOT_REVIEWABLE = "PROPOSAL_REPORT_NOT_REVIEWABLE"
    PROPOSAL_SELF_REPORT_NOT_ALLOWED = "PROPOSAL_SELF_REPORT_NOT_ALLOWED"
    SELF_OFFER_NOT_ALLOWED = "SELF_OFFER_NOT_ALLOWED"
    SMS_SENDER_NOT_CONFIGURED = "SMS_SENDER_NOT_CONFIGURED"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    USER_WITHDRAWAL_BLOCKED = "USER_WITHDRAWAL_BLOCKED"
    VALIDATION_ERROR = "VALIDATION_ERROR"

    # 카탈로그에 없는 HTTP 오류가 봉투를 탈 때 쓰는 방어용 값.
    # 정상 경로에서는 발생하지 않는다.
    HTTP_ERROR = "HTTP_ERROR"

@dataclass(frozen=True)
class ApiErrorSpec:
    http_status: int
    code: ErrorCode
    message: str


class AppError(str, Enum):
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"

    USER_NOT_FOUND = "USER_NOT_FOUND"
    USER_WITHDRAWAL_BLOCKED = "USER_WITHDRAWAL_BLOCKED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    REQUIRED_TERMS_INVALID = "REQUIRED_TERMS_INVALID"

    INVALID_TOKEN = "INVALID_TOKEN"
    INVALID_TOKEN_CREDENTIALS = "INVALID_TOKEN_CREDENTIALS"
    INVALID_TOKEN_TYPE = "INVALID_TOKEN_TYPE"
    MISSING_CREDENTIALS = "MISSING_CREDENTIALS"
    INVALID_AUTHENTICATION_CREDENTIALS = "INVALID_AUTHENTICATION_CREDENTIALS"

    SMS_SENDER_NOT_CONFIGURED = "SMS_SENDER_NOT_CONFIGURED"

    PHONE_ALREADY_EXISTS = "PHONE_ALREADY_EXISTS"
    PHONE_VERIFICATION_NOT_FOUND = "PHONE_VERIFICATION_NOT_FOUND"
    PHONE_VERIFICATION_EXPIRED = "PHONE_VERIFICATION_EXPIRED"
    PHONE_VERIFICATION_CODE_MISMATCH = "PHONE_VERIFICATION_CODE_MISMATCH"
    PHONE_VERIFICATION_SEND_RATE_LIMITED = "PHONE_VERIFICATION_SEND_RATE_LIMITED"
    PHONE_NOT_REGISTERED = "PHONE_NOT_REGISTERED"

    INVALID_DATE_TIME_FORMAT = "INVALID_DATE_TIME_FORMAT"
    PROPOSAL_DEADLINE_INVALID = "PROPOSAL_DEADLINE_INVALID"
    PROPOSAL_ERRAND_FEE_INVALID = "PROPOSAL_ERRAND_FEE_INVALID"
    PROPOSAL_NOT_FOUND = "PROPOSAL_NOT_FOUND"
    PROPOSAL_NOT_EDITABLE = "PROPOSAL_NOT_EDITABLE"
    PROPOSAL_NOT_CANCELLABLE = "PROPOSAL_NOT_CANCELLABLE"
    PROPOSAL_NOT_OPEN = "PROPOSAL_NOT_OPEN"
    PROPOSAL_NOT_MATCHABLE = "PROPOSAL_NOT_MATCHABLE"
    PROPOSAL_NOT_UPDATABLE = "PROPOSAL_NOT_UPDATABLE"
    PROPOSAL_NOT_REPORTABLE = "PROPOSAL_NOT_REPORTABLE"
    PROPOSAL_SELF_REPORT_NOT_ALLOWED = "PROPOSAL_SELF_REPORT_NOT_ALLOWED"
    DUPLICATE_PROPOSAL_REPORT = "DUPLICATE_PROPOSAL_REPORT"
    PROPOSAL_REPORT_NOT_FOUND = "PROPOSAL_REPORT_NOT_FOUND"
    PROPOSAL_REPORT_NOT_REVIEWABLE = "PROPOSAL_REPORT_NOT_REVIEWABLE"
    INVALID_STATUS = "INVALID_STATUS"
    FORBIDDEN = "FORBIDDEN"

    OFFER_NOT_FOUND = "OFFER_NOT_FOUND"
    SELF_OFFER_NOT_ALLOWED = "SELF_OFFER_NOT_ALLOWED"
    DUPLICATE_OFFER = "DUPLICATE_OFFER"
    OFFER_NOT_CANCELLABLE = "OFFER_NOT_CANCELLABLE"
    OFFER_NOT_ACCEPTABLE = "OFFER_NOT_ACCEPTABLE"
    OFFER_NOT_UPDATABLE = "OFFER_NOT_UPDATABLE"

    DISPUTE_EVIDENCE_NOT_FOUND = "DISPUTE_EVIDENCE_NOT_FOUND"

    NOTIFICATION_NOT_FOUND = "NOTIFICATION_NOT_FOUND"


ERRORS: dict[AppError, ApiErrorSpec] = {
    AppError.NOT_FOUND: ApiErrorSpec(
        status.HTTP_404_NOT_FOUND,
        ErrorCode.NOT_FOUND,
        "요청하신 경로를 찾을 수 없습니다.",
    ),
    AppError.METHOD_NOT_ALLOWED: ApiErrorSpec(
        status.HTTP_405_METHOD_NOT_ALLOWED,
        ErrorCode.METHOD_NOT_ALLOWED,
        "허용되지 않은 요청 방식입니다.",
    ),
    AppError.INTERNAL_SERVER_ERROR: ApiErrorSpec(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorCode.INTERNAL_SERVER_ERROR,
        "서버 내부 오류가 발생했습니다.",
    ),
    AppError.USER_NOT_FOUND: ApiErrorSpec(status.HTTP_404_NOT_FOUND, ErrorCode.USER_NOT_FOUND, "사용자를 찾을 수 없습니다."),
    AppError.USER_WITHDRAWAL_BLOCKED: ApiErrorSpec(
        status.HTTP_409_CONFLICT,
        ErrorCode.USER_WITHDRAWAL_BLOCKED,
        "진행 중인 임무, 분쟁 또는 정산이 있어 탈퇴할 수 없습니다. 모든 절차가 완료된 후 다시 이용해주세요.",
    ),
    AppError.VALIDATION_ERROR: ApiErrorSpec(
        status.HTTP_400_BAD_REQUEST,
        ErrorCode.VALIDATION_ERROR,
        "요청 값이 올바르지 않습니다.",
    ),
    AppError.REQUIRED_TERMS_INVALID: ApiErrorSpec(
        status.HTTP_400_BAD_REQUEST,
        ErrorCode.VALIDATION_ERROR,
        "필수 약관에 모두 동의해야 합니다.",
    ),
    AppError.INVALID_TOKEN: ApiErrorSpec(status.HTTP_401_UNAUTHORIZED, ErrorCode.INVALID_TOKEN, "유효하지 않은 토큰입니다."),
    AppError.INVALID_TOKEN_CREDENTIALS: ApiErrorSpec(
        status.HTTP_401_UNAUTHORIZED,
        ErrorCode.INVALID_TOKEN,
        "인증 정보를 확인할 수 없습니다.",
    ),
    AppError.INVALID_TOKEN_TYPE: ApiErrorSpec(status.HTTP_401_UNAUTHORIZED, ErrorCode.INVALID_TOKEN, "토큰 종류가 올바르지 않습니다."),
    AppError.MISSING_CREDENTIALS: ApiErrorSpec(status.HTTP_401_UNAUTHORIZED, ErrorCode.INVALID_TOKEN, "인증 정보가 없습니다."),
    AppError.INVALID_AUTHENTICATION_CREDENTIALS: ApiErrorSpec(
        status.HTTP_401_UNAUTHORIZED,
        ErrorCode.INVALID_TOKEN,
        "인증 정보가 올바르지 않습니다.",
    ),
    AppError.SMS_SENDER_NOT_CONFIGURED: ApiErrorSpec(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorCode.SMS_SENDER_NOT_CONFIGURED,
        "SMS 발신 설정이 완료되지 않았습니다.",
    ),
    AppError.PHONE_ALREADY_EXISTS: ApiErrorSpec(
        status.HTTP_409_CONFLICT,
        ErrorCode.PHONE_ALREADY_EXISTS,
        "이미 가입된 휴대폰 번호입니다.",
    ),
    AppError.PHONE_VERIFICATION_NOT_FOUND: ApiErrorSpec(
        status.HTTP_404_NOT_FOUND,
        ErrorCode.PHONE_VERIFICATION_NOT_FOUND,
        "인증 요청 내역을 찾을 수 없습니다.",
    ),
    AppError.PHONE_VERIFICATION_EXPIRED: ApiErrorSpec(
        status.HTTP_400_BAD_REQUEST,
        ErrorCode.PHONE_VERIFICATION_EXPIRED,
        "인증번호가 만료되었습니다. 다시 요청해주세요.",
    ),
    AppError.PHONE_VERIFICATION_CODE_MISMATCH: ApiErrorSpec(
        status.HTTP_400_BAD_REQUEST,
        ErrorCode.PHONE_VERIFICATION_CODE_MISMATCH,
        "인증번호가 일치하지 않습니다.",
    ),
    AppError.PHONE_VERIFICATION_SEND_RATE_LIMITED: ApiErrorSpec(
        status.HTTP_429_TOO_MANY_REQUESTS,
        ErrorCode.PHONE_VERIFICATION_SEND_RATE_LIMITED,
        "인증번호 요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
    ),
    AppError.PHONE_NOT_REGISTERED: ApiErrorSpec(
        status.HTTP_404_NOT_FOUND,
        ErrorCode.USER_NOT_FOUND,
        "가입되지 않은 휴대폰 번호입니다. 회원가입 후 이용해주세요.",
    ),
    AppError.INVALID_DATE_TIME_FORMAT: ApiErrorSpec(
        status.HTTP_400_BAD_REQUEST,
        ErrorCode.INVALID_DATE_TIME_FORMAT,
        "deadline 형식이 올바르지 않습니다.",
    ),
    AppError.PROPOSAL_DEADLINE_INVALID: ApiErrorSpec(
        status.HTTP_400_BAD_REQUEST,
        ErrorCode.PROPOSAL_DEADLINE_INVALID,
        "마감 시각은 현재 시각보다 이후여야 합니다.",
    ),
    AppError.PROPOSAL_ERRAND_FEE_INVALID: ApiErrorSpec(
        status.HTTP_400_BAD_REQUEST,
        ErrorCode.PROPOSAL_ERRAND_FEE_INVALID,
        "심부름비는 1000원 이상이어야 합니다.",
    ),
    AppError.PROPOSAL_NOT_FOUND: ApiErrorSpec(
        status.HTTP_404_NOT_FOUND,
        ErrorCode.PROPOSAL_NOT_FOUND,
        "요청을 찾을 수 없습니다.",
    ),
    AppError.PROPOSAL_NOT_EDITABLE: ApiErrorSpec(
        status.HTTP_409_CONFLICT,
        ErrorCode.PROPOSAL_NOT_EDITABLE,
        "수정할 수 없는 요청 상태입니다.",
    ),
    AppError.PROPOSAL_NOT_CANCELLABLE: ApiErrorSpec(
        status.HTTP_409_CONFLICT,
        ErrorCode.PROPOSAL_NOT_CANCELLABLE,
        "취소할 수 없는 요청 상태입니다.",
    ),
    AppError.PROPOSAL_NOT_OPEN: ApiErrorSpec(
        status.HTTP_409_CONFLICT,
        ErrorCode.PROPOSAL_NOT_OPEN,
        "지원을 받을 수 없는 요청 상태입니다.",
    ),
    AppError.PROPOSAL_NOT_MATCHABLE: ApiErrorSpec(
        status.HTTP_409_CONFLICT,
        ErrorCode.PROPOSAL_NOT_MATCHABLE,
        "매칭할 수 없는 요청 상태입니다.",
    ),
    AppError.PROPOSAL_NOT_UPDATABLE: ApiErrorSpec(
        status.HTTP_409_CONFLICT,
        ErrorCode.PROPOSAL_NOT_UPDATABLE,
        "업데이트할 수 없는 요청 상태입니다.",
    ),
    AppError.PROPOSAL_NOT_REPORTABLE: ApiErrorSpec(
        status.HTTP_409_CONFLICT,
        ErrorCode.PROPOSAL_NOT_REPORTABLE,
        "신고할 수 없는 요청 상태입니다.",
    ),
    AppError.PROPOSAL_SELF_REPORT_NOT_ALLOWED: ApiErrorSpec(
        status.HTTP_403_FORBIDDEN,
        ErrorCode.PROPOSAL_SELF_REPORT_NOT_ALLOWED,
        "본인의 요청은 신고할 수 없습니다.",
    ),
    AppError.DUPLICATE_PROPOSAL_REPORT: ApiErrorSpec(
        status.HTTP_409_CONFLICT,
        ErrorCode.DUPLICATE_PROPOSAL_REPORT,
        "이미 해당 요청을 신고했습니다.",
    ),
    AppError.PROPOSAL_REPORT_NOT_FOUND: ApiErrorSpec(
        status.HTTP_404_NOT_FOUND,
        ErrorCode.PROPOSAL_REPORT_NOT_FOUND,
        "신고 내역을 찾을 수 없습니다.",
    ),
    AppError.PROPOSAL_REPORT_NOT_REVIEWABLE: ApiErrorSpec(
        status.HTTP_409_CONFLICT,
        ErrorCode.PROPOSAL_REPORT_NOT_REVIEWABLE,
        "이미 처리된 신고입니다.",
    ),
    AppError.INVALID_STATUS: ApiErrorSpec(status.HTTP_400_BAD_REQUEST, ErrorCode.INVALID_STATUS, "입금 확인 대기 상태가 아닙니다."),
    AppError.FORBIDDEN: ApiErrorSpec(status.HTTP_403_FORBIDDEN, ErrorCode.FORBIDDEN, "권한이 없습니다."),
    AppError.OFFER_NOT_FOUND: ApiErrorSpec(status.HTTP_404_NOT_FOUND, ErrorCode.OFFER_NOT_FOUND, "지원 내역을 찾을 수 없습니다."),
    AppError.SELF_OFFER_NOT_ALLOWED: ApiErrorSpec(
        status.HTTP_400_BAD_REQUEST,
        ErrorCode.SELF_OFFER_NOT_ALLOWED,
        "본인의 요청에는 지원할 수 없습니다.",
    ),
    AppError.DUPLICATE_OFFER: ApiErrorSpec(
        status.HTTP_409_CONFLICT,
        ErrorCode.DUPLICATE_OFFER,
        "이미 해당 요청에 지원했습니다.",
    ),
    AppError.OFFER_NOT_CANCELLABLE: ApiErrorSpec(
        status.HTTP_409_CONFLICT,
        ErrorCode.OFFER_NOT_CANCELLABLE,
        "취소할 수 없는 지원 상태입니다.",
    ),
    AppError.OFFER_NOT_ACCEPTABLE: ApiErrorSpec(
        status.HTTP_409_CONFLICT,
        ErrorCode.OFFER_NOT_ACCEPTABLE,
        "수락할 수 없는 지원 상태입니다.",
    ),
    AppError.OFFER_NOT_UPDATABLE: ApiErrorSpec(
        status.HTTP_409_CONFLICT,
        ErrorCode.OFFER_NOT_UPDATABLE,
        "변경할 수 없는 지원 상태입니다.",
    ),
    AppError.DISPUTE_EVIDENCE_NOT_FOUND: ApiErrorSpec(
        status.HTTP_404_NOT_FOUND,
        ErrorCode.DISPUTE_EVIDENCE_NOT_FOUND,
        "분쟁 증빙을 찾을 수 없습니다.",
    ),
    AppError.NOTIFICATION_NOT_FOUND: ApiErrorSpec(
        status.HTTP_404_NOT_FOUND,
        ErrorCode.NOTIFICATION_NOT_FOUND,
        "알림을 찾을 수 없습니다.",
    ),
}


def error_detail(error: AppError, details: str | None = None) -> dict:
    spec = ERRORS[error]
    return {"code": spec.code, "message": spec.message, "details": details}


def api_error(error: AppError, details: str | None = None, headers: dict[str, str] | None = None) -> HTTPException:
    spec = ERRORS[error]
    return HTTPException(
        status_code=spec.http_status,
        detail=error_detail(error, details),
        headers=headers,
    )
