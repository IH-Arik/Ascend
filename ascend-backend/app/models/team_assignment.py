"""My Support Team assignment model.

One record per (operator, pathway). SCS/PT-IM are "locked_on" - assigned
automatically, cannot be disabled (matches "Your SCS and PT/IM are assigned
automatically" on the My Team screen). The 3 optional pathways start
"disabled" and the operator toggles them on/off; every toggle is audit
logged (see app/services/team_service.py).
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


STATUS_LOCKED_ON = "locked_on"
STATUS_ENABLED = "enabled"
STATUS_DISABLED = "disabled"


class TeamAssignment(Document):
    """A single pathway's assignment/enable-state for one operator."""

    user_id: PydanticObjectId
    pathway_key: str
    provider_user_id: PydanticObjectId | None = None
    status: str = "disabled"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "team_assignments"
        indexes = [
            IndexModel([("user_id", 1), ("pathway_key", 1)], unique=True),
        ]
