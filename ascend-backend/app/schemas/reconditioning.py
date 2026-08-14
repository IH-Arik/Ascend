"""Reconditioning plan schemas."""

from datetime import date

from pydantic import BaseModel, Field

PHASES = ("wind_down", "active", "maintenance", "completed")
# Real progression order derived from PHASES' own declared sequence - used
# by RestrictionService to check whether a plan has genuinely reached a
# restriction's required_phase, not a new invented sequence.
PHASE_ORDER: dict[str, int] = {phase: index for index, phase in enumerate(PHASES)}
CLEARANCE_STATUSES = ("pending_review", "no_duty", "modified_duty", "full_duty")
SCS_COORDINATION_STATUSES = ("not_required", "pending", "coordinated")
# Net-new (2026-08-13, not DOCX-sourced) - reuses the same L1-L4 tier
# vocabulary already used for threshold-warning severity elsewhere in this
# codebase, not inventing a second scale.
SEVERITY_LEVELS = ("L1", "L2", "L3", "L4")

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

SCS_COORDINATION_LABELS: dict[str, str] = {
    "not_required": "Not required",
    "pending": "Pending SCS coordination",
    "coordinated": "Coordinated with SCS",
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
    limitation_flag: bool = False
    rehab_strategy_summary: str | None = Field(default=None, max_length=1000)
    scs_coordination_status: str = Field(
        default="not_required", pattern="^(" + "|".join(SCS_COORDINATION_STATUSES) + ")$"
    )
    severity_level: str | None = Field(default=None, pattern="^(" + "|".join(SEVERITY_LEVELS) + ")$")
    injury_reported_on: date | None = None


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
    limitation_flag: bool | None = None
    rehab_strategy_summary: str | None = None
    scs_coordination_status: str | None = None
    scs_coordination_label: str | None = None
    severity_level: str | None = None
    injury_reported_on: str | None = None
    days_out: int | None = None
    updated_at: str | None = None
