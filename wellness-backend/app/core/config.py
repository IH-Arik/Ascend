"""Application configuration loaded from environment variables."""

from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.utils.constants import ACCESS_TOKEN_EXPIRE_MINUTES


class Settings(BaseSettings):
    """Runtime settings for the application."""

    APP_NAME: str = "Dominion Wellness Solutions API"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = ACCESS_TOKEN_EXPIRE_MINUTES

    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "wellness_db"
    MONGODB_TLS: bool = False

    RESEND_API_KEY: str = "your-resend-api-key"
    FROM_EMAIL: str = "noreply@example.com"

    OPENAI_API_KEY: str = "your-openai-api-key"
    OPENAI_MODEL: str = "gpt-4o-mini"

    AWS_ACCESS_KEY_ID: str = "your-aws-access-key-id"
    AWS_SECRET_ACCESS_KEY: str = "your-aws-secret-access-key"
    AWS_BUCKET_NAME: str = "your-aws-bucket-name"
    AWS_REGION: str = "us-east-1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug_value(cls, value: Any) -> bool:
        """Parse flexible DEBUG values from environment sources."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on", "debug"}:
                return True
            if normalized in {"false", "0", "no", "off", "release", "production"}:
                return False
        raise ValueError("DEBUG must be a boolean-compatible value.")


settings = Settings()
