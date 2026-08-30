"""PT session schemas."""

from datetime import date

from pydantic import BaseModel, Field

FOCUS_AREAS = ("strength", "conditioning", "mobility", "recovery", "assessment")
FOCUS_LABELS: dict[str, str] = {
    "strength": "Strength",
    "conditioning": "Conditioning",
    "mobility": "Mobility",
    "recovery": "Recovery",
    "assessment": "Assessment",
}
SESSION_STATUSES = ("scheduled", "completed", "cancelled")


class PTSessionCreate(BaseModel):
    """Schedule a real group training session."""

    lead_provider_id: str | None = Field(default=None, description="Defaults to the creating provider.")
    session_date: date
    start_time: str = Field(pattern=r"^([01]\d|2[0-3])[0-5]\d$", description="24h HHMM, e.g. '0600'.")
    group_label: str = Field(min_length=1, max_length=80)
    focus: str = Field(pattern="^(" + "|".join(FOCUS_AREAS) + ")$")
    capacity: int = Field(gt=0, le=100)
    unit_id: str | None = None


class PTSessionAttendeeAdd(BaseModel):
    """Enroll one real attendee in a session."""

    user_id: str


class PTSessionUpdate(BaseModel):
    """Update a session's status or capacity."""

    status: str | None = Field(default=None, pattern="^(" + "|".join(SESSION_STATUSES) + ")$")
    capacity: int | None = Field(default=None, gt=0, le=100)


class PTSessionResponse(BaseModel):
    """A single scheduled group training session."""

    id: str
    lead_provider_id: str
    lead_provider_name: str | None
    lead_provider_role: str
    session_date: str
    start_time: str
    group_label: str
    focus: str
    focus_label: str
    capacity: int
    enrolled_count: int
    capacity_pct: float
    status: str
    created_at: str
