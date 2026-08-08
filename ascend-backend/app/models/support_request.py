"""Support request persistence model ("Talk to your team" submissions)."""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class SupportRequest(Document):
    """A user-initiated request to a support pathway."""

    user_id: PydanticObjectId
    pathway_key: str
    pathway_label: str
    message: str | None = None
    status: str = "open"
    priority_flag: bool = False
    safety_flag_terms: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "support_requests"
        indexes = [
            IndexModel([("user_id", 1), ("created_at", -1)]),
        ]
