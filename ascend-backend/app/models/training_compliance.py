"""Staff training compliance tracker (DOCX Section 14: AT Level I, OPSEC
Initial Training, OPSEC Annual Refresher).

Real, per-staff-member record for one required training item. Distinct
from `ProviderCredential` (BLS/professional certifications, DOCX 1.4.7) -
that model has no due-date/submission-status concept, and these 3 training
types are a separate DOCX-named compliance category with their own fields.
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

TRAINING_TYPES = ("at_level_1", "opsec_initial", "opsec_annual_refresher")
SUBMISSION_STATUSES = ("pending", "submitted", "approved", "rejected")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class TrainingCompliance(Document):
    """One required training item's real due/completion/submission state for one staff member."""

    user_id: PydanticObjectId
    training_type: str
    due_date: date
    completion_date: date | None = None
    certificate_uploaded: bool = False
    submitted_to: str | None = None
    submission_status: str = "pending"
    # Only meaningful for opsec_annual_refresher - the next cycle's due date,
    # set once this cycle is completed.
    renewal_due_date: date | None = None
    recorded_by: PydanticObjectId
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "training_compliance"
        indexes = [
            IndexModel([("user_id", 1), ("training_type", 1)], unique=True),
        ]
