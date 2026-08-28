"""Admin authentication router. 인증 없이 접근하는 유일한 관리자 경로다."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.core.openapi import ADMIN_LOGIN_EXAMPLE, error_responses, success_response
from app.schemas.admin import AdminLoginRequest
from app.schemas.common import ApiResponse
from app.schemas.user import AuthTokenResponse
from app.services.admin.admin_auth_service import AdminAuthService


router = APIRouter(prefix="/admin/auth", tags=["관리자"])


@router.post(
    "/login",
    response_model=ApiResponse[AuthTokenResponse],
    summary="관리자 로그인",
    description=(
        "관리자 아이디와 비밀번호로 액세스 토큰과 리프레시 토큰을 발급합니다. "
        "액세스 토큰 재발급은 일반 사용자와 같은 `POST /v1/auth/refresh`를 사용합니다."
    ),
    responses={
        200: success_response(ADMIN_LOGIN_EXAMPLE),
        **error_responses(
            AppError.VALIDATION_ERROR,
            AppError.ADMIN_CREDENTIALS_INVALID,
            AppError.ADMIN_LOGIN_LOCKED,
        ),
    },
)
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)) -> ApiResponse[AuthTokenResponse]:
    return ApiResponse(success=True, data=AdminAuthService.login(db, payload.username, payload.password))
