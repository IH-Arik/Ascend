"""Staff training compliance schemas (DOCX Section 14)."""

from datetime import date

from pydantic import BaseModel, Field

from app.models.training_compliance import SUBMISSION_STATUSES, TRAINING_TYPES


class TrainingComplianceUpsert(BaseModel):
    """Admin records or updates one staff member's training item."""

    training_type: str = Field(pattern="^(" + "|".join(TRAINING_TYPES) + ")$")
    due_date: date
    completion_date: date | None = None
    certificate_uploaded: bool = False
    submitted_to: str | None = Field(default=None, max_length=120)
    submission_status: str = Field(default="pending", pattern="^(" + "|".join(SUBMISSION_STATUSES) + ")$")
    renewal_due_date: date | None = None


class TrainingComplianceResponse(BaseModel):
    """A single staff member's training item."""

    id: str
    user_id: str
    user_name: str | None
    training_type: str
    due_date: str
    completion_date: str | None
    certificate_uploaded: bool
    submitted_to: str | None
    submission_status: str
    renewal_due_date: str | None
    is_overdue: bool
    updated_at: str
