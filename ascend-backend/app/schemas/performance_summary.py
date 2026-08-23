"""Medical History Performance Summary schemas (DOCX data dictionary)."""

from datetime import date

from pydantic import BaseModel, Field

from app.models.performance_summary import VISIBILITY_LEVELS


class PerformanceSummaryCreate(BaseModel):
    """PT/IM (or Admin) authors a summary for an operator.

    `user_id`, `created_by`, `reviewer_role`, and `review_date` are all set
    server-side from the real caller and target - never client-supplied,
    same pattern as `SpecialistNote` and `Recommendation.assigned_by`.
    """

    injury_history_summary: str | None = Field(default=None, max_length=2000)
    limitations_summary: str | None = Field(default=None, max_length=2000)
    return_to_performance_considerations: str | None = Field(default=None, max_length=2000)
    nutrition_considerations: str | None = Field(default=None, max_length=2000)
    sleep_recovery_considerations: str | None = Field(default=None, max_length=2000)
    medication_allergy_considerations_if_authorized: str | None = Field(
        default=None, max_length=2000
    )
    specialist_notes_link: list[str] = Field(default_factory=list)
    expiration_or_review_due_date: date | None = None


class PerformanceSummaryUpdate(BaseModel):
    """Move a summary's real approved visibility level."""

    approved_visibility_level: str = Field(
        pattern="^(" + "|".join(VISIBILITY_LEVELS) + ")$"
    )
