import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.database import SessionLocal
from app.core.firebase import get_fcm_service, get_notification_worker, init_fcm
from app.api.v1.router import api_router
from app.core.exceptions import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.listeners import admin_alert_listener, notification_listener
from app.schemas.common import ApiResponse
from app.services.chat.chat_push import register_chat_consumers
from app.services.outbox.consumers import consumer_registry
from app.services.outbox.worker import OutboxWorker, register_outbox_jobs, set_wake_callback
from app.tasks.payment_checker import (
    check_and_cancel_expired_payment_proposals,
    send_pending_payment_reminders,
)
from app.core.openapi import (
    HEALTH_EXAMPLE,
    ROOT_EXAMPLE,
    apply_global_error_responses,
    restore_example_nulls,
    success_response,
)

setup_logging()

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()


#: `CORS_ALLOW_ORIGINS`가 비었을 때 development에서만 쓰는 기본값. 관리자 웹 로컬 개발 서버다.
DEFAULT_DEV_CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]


def _api_docs_enabled() -> bool:
    return settings.app_env.lower() != "production"


def _cors_allow_origins() -> list[str]:
    """허용 Origin 목록을 만든다.

    와일드카드를 허용하지 않는 이유: `allow_origins=["*"]`와 `allow_credentials=True`를 같이
    쓰면 Starlette은 와일드카드를 못 쓴다는 걸 알고 요청 Origin을 그대로 반사한다. 그러면 아무
    도메인이나 자격증명을 실어 보내고 응답을 읽을 수 있다.

    미설정일 때 조용히 빈 목록으로 뜨지 않고 죽이는 이유: 빈 목록은 배포 후에 원인 모를 CORS
    오류로만 드러난다. 기동 시점에 실패하면 무엇이 빠졌는지 바로 보인다.
    """
    origins = settings.cors_allow_origin_list

    if "*" in origins:
        raise RuntimeError(
            "CORS_ALLOW_ORIGINS에 와일드카드(*)는 쓸 수 없습니다. 허용할 Origin을 명시하세요."
        )
    if origins:
        return origins
    if settings.app_env.lower() == "development":
        return DEFAULT_DEV_CORS_ORIGINS

    raise RuntimeError(
        f"CORS_ALLOW_ORIGINS가 비어 있습니다. APP_ENV={settings.app_env} 환경에서는 "
        "허용할 Origin을 반드시 지정해야 합니다."
    )


def _api_docs_path() -> str | None:
    return "/docs" if _api_docs_enabled() else None


def _ensure_admin_account() -> None:
    """설정된 관리자 계정이 없으면 만든다. 없어도 앱 기동은 막지 않는다."""
    from app.core.database import SessionLocal
    from app.services.admin.admin_auth_service import AdminAuthService

    db = SessionLocal()
    try:
        AdminAuthService.ensure_admin_account(db)
    except Exception:  # noqa: BLE001 - 기동 실패로 번지지 않게 한다
        logger.exception("관리자 계정 보증에 실패했습니다.")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    notification_listener.register_all()
    admin_alert_listener.register_all()

    if not settings.admin_alert_slack_webhook_url:
        logger.warning(
            "ADMIN_ALERT_SLACK_WEBHOOK_URL not configured — 분쟁·임무 완료 관리자 알림이 발송되지 않습니다"
        )

    _ensure_admin_account()

    if settings.fcm_credentials_path or settings.fcm_credentials_json:
        init_fcm()
    else:
        logger.warning("FCM credentials not configured — push notifications disabled")

    worker = get_notification_worker()
    _scheduler.add_job(
        worker.retry_failed,
        "interval",
        minutes=5,
        args=[SessionLocal],
        id="retry_failed_notifications",
        replace_existing=True,
    )
    _scheduler.add_job(
        check_and_cancel_expired_payment_proposals,
        "interval",
        hours=1,
        args=[SessionLocal],
        id="cancel_expired_payment_proposals",
        replace_existing=True,
    )
    _scheduler.add_job(
        send_pending_payment_reminders,
        "interval",
        minutes=10,
        args=[SessionLocal],
        id="send_pending_payment_reminders",
        replace_existing=True,
    )
    if settings.outbox_worker_enabled:
        _start_outbox_worker()

    _scheduler.start()

    yield

    set_wake_callback(None)

    _scheduler.shutdown(wait=False)


def _start_outbox_worker() -> None:
    """채팅 전달 대상을 등록하고, 공통 Outbox 주기 작업(10초 처리, 매일 04:00 정리)과 커밋 직후 깨우기를 연결한다."""
    register_chat_consumers(consumer_registry, SessionLocal, get_fcm_service())
    register_outbox_jobs(_scheduler, OutboxWorker(SessionLocal))


# Create FastAPI app
app = FastAPI(
    lifespan=lifespan,
    title="OrderRun API",
    description=(
        "심부름 요청, 지원, 임무, 인증을 제공하는 OrderRun 백엔드 API입니다.\n\n"
        "모든 실패 응답은 `success`/`error`/`timestamp` 봉투로 나갑니다. "
        "클라이언트는 `error.code`로만 분기하고 `error.message`는 표시용으로만 사용합니다.\n\n"
        "아래 두 코드는 매칭되는 엔드포인트가 없을 때 발생해 개별 API 문서에 표시되지 않습니다.\n"
        "- `NOT_FOUND` (404): 존재하지 않는 경로를 호출한 경우\n"
        "- `METHOD_NOT_ALLOWED` (405): 허용되지 않은 HTTP 메서드로 호출한 경우\n"
        "- `HTTP_ERROR`: 카탈로그에 없는 HTTP 오류에 대한 방어용 값. 정상 경로에서는 발생하지 않습니다\n\n"
        "전체 코드 목록은 저장소의 `docs/api-spec/error-codes.md`를 정본으로 합니다."
    ),
    version="0.1.0",
    docs_url=_api_docs_path(),
    redoc_url="/redoc" if _api_docs_enabled() else None,
    openapi_url="/openapi.json" if _api_docs_enabled() else None,
)

# CORS middleware
# 허용 Origin은 환경변수로만 정한다. 관리자 웹 도메인이 환경마다 다르고 이 저장소에 없다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Exception handlers
# StarletteHTTPException까지 등록해야 라우트 404/405도 응답 봉투를 탄다.
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Include versioned API routes
app.include_router(api_router)


@app.get("/", responses={200: success_response(ROOT_EXAMPLE)})
async def root():
    """API 루트 정보를 반환합니다."""
    return {
        "message": "Welcome to OrderRun API",
        "version": "0.1.0",
        "docs": _api_docs_path(),
    }


@app.get(
    "/v1/health",
    response_model=ApiResponse[dict[str, str]],
    responses={200: success_response(HEALTH_EXAMPLE)},
)
async def health_check():
    """서버 상태를 확인합니다."""
    return ApiResponse(success=True, data={"status": "UP"}, message="Success")


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    restore_example_nulls(openapi_schema, app.routes)
    apply_global_error_responses(openapi_schema)

    for path_item in openapi_schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            operation.get("responses", {}).pop("422", None)

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=settings.app_debug,
    )
