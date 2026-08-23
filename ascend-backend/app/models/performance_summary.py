"""Medical History Performance Summary model (DOCX data dictionary + Table 23).

DOCX: "Allow the PT/IM or authorized reviewer to create a structured
medical-history performance summary that translates uploaded medical history
into actionable performance considerations without exposing unnecessary raw
medical details."

Fields match the DOCX data dictionary entry verbatim ("summary_id, user_id,
created_by, reviewer_role, review_date, approved_visibility_level,
injury_history_summary, limitations_summary,
return_to_performance_considerations, nutrition_considerations,
sleep_recovery_considerations, medication_allergy_considerations_if_authorized,
specialist_notes_link, expiration_or_review_due_date") - `summary_id` is
Beanie's own `id`, and `specialist_notes_link` points at the real
`SpecialistNote` collection built earlier rather than being a free-text URL.

The whole point of the entity is minimum-necessary disclosure, so no role
except PT/IM (the authoring clinical role) and Admin ever receives every
field - see `ROLE_VISIBLE_FIELDS` in
`app/services/performance_summary_service.py`, which encodes DOCX Table 23's
per-role row directly.
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


# DOCX Table 23 grades disclosure per role rather than as a single on/off,
# and the data dictionary carries `approved_visibility_level` as a real
# field. These are the three real levels that row implies: nothing released
# yet, the performance-relevant guidance released, and the additionally
# authorized medication/allergy content released.
VISIBILITY_LEVELS = ("draft", "approved", "approved_with_medical")

REVIEW_DUE_DEFAULT_DAYS = 180


class PerformanceSummary(Document):
    """A PT/IM-authored, role-scoped performance summary of medical history."""

    user_id: PydanticObjectId
    created_by: PydanticObjectId
    reviewer_role: str
    review_date: date = Field(default_factory=date.today)
    approved_visibility_level: str = "draft"

    injury_history_summary: str | None = None
    limitations_summary: str | None = None
    return_to_performance_considerations: str | None = None
    nutrition_considerations: str | None = None
    sleep_recovery_considerations: str | None = None
    # DOCX names this field "..._if_authorized" - it is the one field gated
    # behind the highest visibility level, never released at "approved".
    medication_allergy_considerations_if_authorized: str | None = None

    # DOCX: "specialist_notes_link". A real reference to the existing
    # `SpecialistNote` documents rather than an invented free-text link.
    specialist_notes_link: list[PydanticObjectId] = Field(default_factory=list)

    expiration_or_review_due_date: date | None = None

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "performance_summaries"
        indexes = [
            IndexModel([("user_id", 1), ("review_date", -1)]),
        ]
