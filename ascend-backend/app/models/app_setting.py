"""Application setting document model."""

from datetime import datetime, timezone

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class AppSetting(Document):
    """Simple key-value settings document for operational config."""

    key: str
    value: str | int | float | bool | dict | list | None = None
    description: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "app_settings"
        indexes = [IndexModel([("key", 1)], unique=True)]
