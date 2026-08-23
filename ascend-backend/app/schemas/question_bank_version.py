"""Question Bank Version schemas (DOCX Table 22 data dictionary)."""

from datetime import date

from pydantic import BaseModel, Field


class QuestionBankVersionCreate(BaseModel):
    """Admin creates a new versioned, effective-dated question bank record.

    `approved_by` is not client-supplied - it is set server-side from the
    real authenticated caller, same pattern as `Recommendation.assigned_by`.
    """

    version_id: str = Field(min_length=1, max_length=40)
    effective_date: date = Field(default_factory=date.today)
    onboarding_question_set_id: str | None = Field(default=None, max_length=80)
    daily_question_set_id: str | None = Field(default=None, max_length=80)
    weekly_question_set_id: str | None = Field(default=None, max_length=80)
    monthly_question_set_id: str | None = Field(default=None, max_length=80)
    change_reason: str | None = Field(default=None, max_length=500)
