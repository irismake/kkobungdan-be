from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application
    app_env: str = "development"
    app_debug: bool = True
    secret_key: str

    # Logging
    log_level: str = "INFO"
    log_dir: str = "/app/logs"
    log_file_enabled: bool = False
    log_retention_days: int = 14

    # Database
    db_host: str = "localhost"
    db_port: int = 3306
    db_username: str
    db_password: str
    db_name: str

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # 관리자 계정. 기동 시 이 아이디의 관리자 사용자가 없으면 만든다.
    admin_username: Optional[str] = None
    admin_initial_password: Optional[str] = None

    # 관리자 웹에 노출하는 플랫폼 입금 계좌. 요청별 데이터가 아니라 운영 설정값이다.
    admin_deposit_bank_name: Optional[str] = None
    admin_deposit_account_number: Optional[str] = None
    admin_deposit_account_holder: Optional[str] = None

    # 관리자 운영 알림(Slack Incoming Webhook). 비어 있으면 발송을 건너뛴다.
    # URL 자체가 인증 수단이므로 저장소에 두지 않고 환경변수로만 받는다.
    admin_alert_slack_webhook_url: Optional[str] = None
    # 알림 메시지에 붙일 관리자 웹 주소. 비어 있으면 링크 줄을 빼고 보낸다.
    admin_web_base_url: Optional[str] = None

    # FCM (Firebase Cloud Messaging)
    fcm_credentials_path: Optional[str] = None   # 로컬 개발: 파일 경로
    fcm_credentials_json: Optional[str] = None   # 배포 환경: JSON 문자열 (GitHub Secret)

    # AWS SNS (SMS)
    aws_sns_region: str = "ap-northeast-2"
    aws_sns_access_key_id: str
    aws_sns_secret_access_key: str
    aws_sns_sms_sender_id: str
    aws_sns_sms_type: str = "Transactional"

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # CORS 허용 Origin. 쉼표로 구분한다. 와일드카드는 받지 않는다.
    # 비워 두면 development에서만 로컬 기본값으로 뜨고, 그 외 환경에서는 기동에 실패한다.
    cors_allow_origins: str = ""

    # Payment
    payment_bank_name: str = "국민은행"
    payment_account_number: str = "123-456-789012"
    payment_account_holder: str = "주식회사 오더런"

    @property
    def cors_allow_origin_list(self) -> list[str]:
        """`CORS_ALLOW_ORIGINS`를 목록으로 판다. 빈 항목은 버린다."""
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        """Construct database URL for SQLAlchemy."""
        return (
            f"mysql+pymysql://{self.db_username}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?charset=utf8mb4"
        )

    @property
    def database_url_sync(self) -> str:
        """Synchronous database URL for Alembic."""
        return self.database_url


# Global settings instance
settings = Settings()
