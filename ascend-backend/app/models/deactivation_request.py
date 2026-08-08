"""Account deactivation request model (DOCX: "deactivation queue", section 14 Admin Panel).

DOCX: "Login, password reset, account activation/deactivation..." and the
Admin Panel module lists a "deactivation queue" as something Admin views and
acts on. A user requests deactivation; only DWS Admin can approve it - never
self-service immediate deactivation, and no record is ever deleted.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class DeactivationRequest(Document):
    """A user-initiated request to deactivate their own account, pending Admin approval."""

    user_id: PydanticObjectId
    reason: str | None = None
    status: str = "pending"
    requested_at: datetime = Field(default_factory=utc_now)
    reviewed_at: datetime | None = None
    reviewed_by: PydanticObjectId | None = None

    class Settings:
        """Beanie collection settings."""

        name = "deactivation_requests"
        indexes = [
            IndexModel([("user_id", 1), ("status", 1)]),
        ]
