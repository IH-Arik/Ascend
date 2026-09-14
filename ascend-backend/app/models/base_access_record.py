"""Base access / badge / pass tracker (DOCX Section 14 Compliance Item:
"Base Access / Badge / Pass" - request_date, approval_status,
expiration_date, return_required, returned_date).

Same real, per-staff-member record pattern as `TrainingCompliance` - a
distinct DOCX-named compliance category with its own field set, not a
reuse of `TrainingCompliance` or `ProviderCredential`.
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

APPROVAL_STATUSES = ("pending", "approved", "denied", "revoked")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class BaseAccessRecord(Document):
    """One staff member's real base access / badge / pass request and closeout state."""

    user_id: PydanticObjectId
    request_date: date
    approval_status: str = "pending"
    expiration_date: date | None = None
    return_required: bool = True
    returned_date: date | None = None
    recorded_by: PydanticObjectId
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "base_access_records"
        indexes = [
            IndexModel([("user_id", 1), ("created_at", -1)]),
        ]
