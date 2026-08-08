"""Reconditioning plan schemas."""

from datetime import date

from pydantic import BaseModel, Field

PHASES = ("wind_down", "active", "maintenance", "completed")
CLEARANCE_STATUSES = ("pending_review", "no_duty", "modified_duty", "full_duty")

PHASE_LABELS: dict[str, str] = {
    "wind_down": "Wind-down protocol",
    "active": "Active reconditioning",
    "maintenance": "Maintenance",
    "completed": "Completed",
}

CLEARANCE_LABELS: dict[str, str] = {
    "pending_review": "Pending PT/IM review",
    "no_duty": "No duty",
    "modified_duty": "Modified duty",
    "full_duty": "Full duty",
}


class ReconditioningPlanUpdate(BaseModel):
    """PT/IM or SCS updates a user's reconditioning plan."""

    phase: str = Field(pattern="^(" + "|".join(PHASES) + ")$")
    sessions_completed: int = Field(ge=0)
    sessions_total: int = Field(ge=0)
    cadence_note: str | None = Field(default=None, max_length=120)
    injury_flags: list[str] = Field(default_factory=list, max_length=10)
    ptim_clearance_status: str = Field(pattern="^(" + "|".join(CLEARANCE_STATUSES) + ")$")
    next_review_date: date | None = None


class ReconditioningPlanResponse(BaseModel):
    """A user's current reconditioning plan status."""

    available: bool
    phase: str | None = None
    phase_label: str | None = None
    days_in_phase: int | None = None
    sessions_completed: int | None = None
    sessions_total: int | None = None
    cadence_note: str | None = None
    injury_flags: list[str] | None = None
    ptim_clearance_status: str | None = None
    ptim_clearance_label: str | None = None
    next_review_date: str | None = None
    updated_at: str | None = None
