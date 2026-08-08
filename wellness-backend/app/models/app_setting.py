"""App-level editable settings content models."""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import ConfigDict, Field


class AppSetting(Document):
    """Persist editable superadmin-managed application content."""

    key: str
    title: str
    content: str
    image_url: str | None = None
    updated_by_user_id: PydanticObjectId | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        """Beanie collection settings."""

        name = "app_settings"
