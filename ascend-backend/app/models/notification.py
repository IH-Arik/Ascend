"""In-app notification persistence model (docs/NOTIFICATION_RULES.md)."""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Notification(Document):
    """A single in-app notification for one user."""

    user_id: PydanticObjectId
    family: str
    title: str
    body: str
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    is_read: bool = False
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "notifications"
        indexes = [
            IndexModel([("user_id", 1), ("created_at", -1)]),
            IndexModel([("user_id", 1), ("is_read", 1)]),
        ]
