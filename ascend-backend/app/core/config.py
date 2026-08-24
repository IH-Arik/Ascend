"""Application configuration."""

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = Field(default="Ascend Backend", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8010, alias="APP_PORT")
    cors_origins: list[str] = Field(default=["*"], alias="CORS_ORIGINS")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    secret_key: str = Field(default="change-me", alias="SECRET_KEY")
    superadmin_email: str = Field(default="", alias="SUPERADMIN_EMAIL")
    access_token_expire_minutes: int = Field(
        default=60,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    refresh_token_expire_minutes: int = Field(
        default=10080,
        alias="REFRESH_TOKEN_EXPIRE_MINUTES",
    )
    mongodb_url: str = Field(default="mongodb://localhost:27017", alias="MONGODB_URL")
    mongodb_db_name: str = Field(default="ascend_db", alias="MONGODB_DB_NAME")
    mongodb_tls: bool = Field(default=False, alias="MONGODB_TLS")
    db_required: bool = Field(default=False, alias="DB_REQUIRED")
    redis_url: str = Field(default="", alias="REDIS_URL")
    login_email: str = Field(default="", alias="LOGIN_EMAIL")
    gmail_sender_email: str = Field(default="", alias="GMAIL_SENDER_EMAIL")
    gmail_client_id: str = Field(default="", alias="GMAIL_CLIENT_ID")
    gmail_client_secret: str = Field(default="", alias="GMAIL_CLIENT_SECRET")
    gmail_refresh_token: str = Field(default="", alias="GMAIL_REFRESH_TOKEN")
    support_email: str = Field(default="", alias="SUPPORT_EMAIL")
    support_phone: str = Field(default="", alias="SUPPORT_PHONE")
    help_center_url: str = Field(default="", alias="HELP_CENTER_URL")
    terms_of_use_url: str = Field(default="", alias="TERMS_OF_USE_URL")
    privacy_policy_url: str = Field(default="", alias="PRIVACY_POLICY_URL")
    ai_provider_api_key: str = Field(default="", alias="AI_PROVIDER_API_KEY")
    anthropic_model: str = Field(default="claude-sonnet-4-6", alias="ANTHROPIC_MODEL")
    policy_version: str = Field(default="ascend-ia-01@1.4.0", alias="POLICY_VERSION")
    medical_record_storage_dir: str = Field(
        default="./storage/medical_records", alias="MEDICAL_RECORD_STORAGE_DIR"
    )
    medical_record_max_bytes: int = Field(
        default=50 * 1024 * 1024, alias="MEDICAL_RECORD_MAX_BYTES"
    )
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    resend_from_address: str = Field(default="onboarding@resend.dev", alias="RESEND_FROM_ADDRESS")
    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: str = Field(default="", alias="TWILIO_FROM_NUMBER")
    fcm_server_key: str = Field(default="", alias="FCM_SERVER_KEY")
    opsec_notice_text: str = Field(
        default=(
            "Protect sensitive readiness, mission, and personal information. "
            "Do not share OPSEC or CUI through unauthorized channels."
        ),
        alias="OPSEC_NOTICE_TEXT",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("app_debug", "mongodb_tls", "db_required", mode="before")
    @classmethod
    def parse_bool_values(cls, value: Any) -> bool:
        """Parse flexible boolean values from environment sources."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        raise ValueError("Expected a boolean-compatible value.")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        """Parse CORS origins from a comma-separated string or list."""
        if isinstance(value, str):
            if not value.strip():
                return ["*"]
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value]
        return ["*"]


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
