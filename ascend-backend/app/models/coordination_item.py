"""PT/IM-SCS coordination item model.

Net-new (2026-09-07, explicit user go-ahead - not DOCX-sourced). A joint
item raised whenever pain, a functional limitation, a failed OFT, or a
recovery decline affects a training-plan decision that PT/IM and SCS must
agree on. Deliberately its own record - never folded into operator
messaging, `Recommendation`, or `IdmtHandoff`, which each cover a different
real workflow. Both PT/IM and SCS providers assigned to the same operator
see the identical record (no per-role view split), and only the two of them
(plus Admin) can touch it - matching the reconditioning plan's existing
joint-authorship model in `reconditioning_plan.py`.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

TRIGGER_CATEGORIES = ("pain", "limitation", "failed_oft", "recovery_decline")
AFFECTS_CATEGORIES = ("training_load", "session_plan", "assessment", "programming")
COORDINATION_STATUSES = ("awaiting_response", "acknowledged", "closed")
COORDINATION_ROLES = ("PT/IM", "SCS")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class CoordinationItem(Document):
    """A single joint PT/IM-SCS training-decision coordination item."""

    user_id: PydanticObjectId
    title: str = Field(min_length=1, max_length=160)
    trigger_category: str
    trigger_detail: str | None = Field(default=None, max_length=120)
    affects: str
    raised_by: PydanticObjectId
    raised_by_role: str
    # Whichever role currently needs to act - starts as the role NOT raising
    # the item (you don't raise an item and assign it to yourself).
    pending_with_role: str
    status: str = "awaiting_response"
    acknowledged_by: PydanticObjectId | None = None
    acknowledged_at: datetime | None = None
    closed_by: PydanticObjectId | None = None
    closed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "coordination_items"
        indexes = [
            IndexModel([("user_id", 1), ("status", 1)]),
            IndexModel([("updated_at", -1)]),
        ]
