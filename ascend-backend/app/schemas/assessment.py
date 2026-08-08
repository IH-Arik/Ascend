"""Operator assessment tracking schemas (DOCX section 8.1).

Assessment results are always qualitative to the end user (`result_band`,
never a raw numeric score) - canonical scoring, if any exists for an
assessment type, stays backend/provider-side only.
"""

from datetime import date

from pydantic import BaseModel, Field

ASSESSMENT_TYPES = (
    "initial",
    "annual_follow_up",
    "quarterly_readiness_check",
    "strength_reassessment",
    "cardio_reassessment",
    "recovery_baseline",
)

ASSESSMENT_TYPE_LABELS: dict[str, str] = {
    "initial": "Initial HPO/H2F assessment",
    "annual_follow_up": "Annual follow-up assessment",
    "quarterly_readiness_check": "Quarterly readiness check",
    "strength_reassessment": "Strength re-assessment",
    "cardio_reassessment": "Cardio re-assessment",
    "recovery_baseline": "Recovery baseline",
}

RESULT_BAND_LABELS: dict[str, str] = {
    "strong": "Above target",
    "steady": "On target",
    "flagged": "Needs focus",
}


class AssessmentScheduleRequest(BaseModel):
    """Schedule an assessment for a user."""

    assessment_type: str = Field(pattern="^(" + "|".join(ASSESSMENT_TYPES) + ")$")
    due_date: date
    scheduled_date: date | None = None


class AssessmentCompleteRequest(BaseModel):
    """Record a completed assessment result."""

    completed_date: date
    result_band: str = Field(pattern="^(strong|steady|flagged)$")
    physical_result_summary: str | None = Field(default=None, max_length=500)
    mental_result_summary: str | None = Field(default=None, max_length=500)
    feedback_session_status: str = Field(
        default="pending", pattern="^(offered|completed|declined|pending)$"
    )


class AssessmentResponse(BaseModel):
    """A single assessment record, qualitative summary only."""

    id: str
    assessment_type: str
    display_title: str
    status: str
    due_date: str | None
    scheduled_date: str | None
    completed_date: str | None
    result_band: str | None
    result_band_label: str | None
    physical_result_summary: str | None
    mental_result_summary: str | None
    feedback_session_status: str
