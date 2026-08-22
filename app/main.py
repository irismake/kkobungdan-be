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
from app.core.firebase import get_notification_worker, init_fcm
from app.api.v1.router import api_router
from app.core.exceptions import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.listeners import notification_listener
from app.schemas.common import ApiResponse
from app.tasks.payment_checker import (
    check_and_cancel_expired_payment_proposals,
    send_pending_payment_reminders,
)
from app.core.openapi import (
    HEALTH_EXAMPLE,
    ROOT_EXAMPLE,
    apply_global_error_responses,
    success_response,
)

setup_logging()

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()


def _api_docs_enabled() -> bool:
    return settings.app_env.lower() != "production"


def _api_docs_path() -> str | None:
    return "/docs" if _api_docs_enabled() else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    notification_listener.register_all()

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
    _scheduler.start()

    yield

    _scheduler.shutdown(wait=False)


# Create FastAPI app
app = FastAPI(
    lifespan=lifespan,
    title="OrderRun API",
    description=(
        "심부름 요청, 지원, 미션, 인증을 제공하는 OrderRun 백엔드 API입니다.\n\n"
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    apply_global_error_responses(openapi_schema)

    for path_item in openapi_schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            operation.get("responses", {}).pop("422", None)
            for response in operation.get("responses", {}).values():
                examples = response.get("content", {}).get("application/json", {}).get("examples", {})
                for example in examples.values():
                    error = example.get("value", {}).get("error")
                    if isinstance(error, dict) and "details" not in error:
                        error["details"] = None

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
