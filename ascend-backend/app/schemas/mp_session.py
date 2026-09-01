"""Mental Performance session schemas."""

from datetime import date

from pydantic import BaseModel, Field, model_validator

SESSION_TYPES = ("individual", "group")
SESSION_STATUSES = ("scheduled", "completed", "escalated", "cancelled", "no_show")


class MPSessionCreate(BaseModel):
    """Schedule a real Mental Performance session, individual or group."""

    session_date: date
    start_time: str = Field(pattern=r"^([01]\d|2[0-3])[0-5]\d$", description="24h HHMM, e.g. '0930'.")
    session_type: str = Field(pattern="^(" + "|".join(SESSION_TYPES) + ")$", default="individual")
    attendee_user_ids: list[str] = Field(default_factory=list)
    group_label: str | None = Field(default=None, max_length=80)
    topic: str | None = Field(default=None, max_length=120)
    capacity: int | None = Field(default=None, gt=0, le=100)

    @model_validator(mode="after")
    def _validate_shape(self) -> "MPSessionCreate":
        if self.session_type == "individual" and len(self.attendee_user_ids) != 1:
            raise ValueError("An individual session must have exactly one attendee.")
        if self.session_type == "group" and not self.group_label:
            raise ValueError("A group session requires a group_label.")
        return self


class MPSessionUpdate(BaseModel):
    """Update a session's status."""

    status: str | None = Field(default=None, pattern="^(" + "|".join(SESSION_STATUSES) + ")$")


class MPSessionResponse(BaseModel):
    """A single scheduled Mental Performance session."""

    id: str
    provider_id: str
    provider_name: str | None
    provider_role: str
    session_date: str
    start_time: str
    session_type: str
    attendee_user_ids: list[str]
    attendee_count: int
    group_label: str | None
    topic: str | None
    capacity: int | None
    capacity_pct: float | None
    status: str
    created_at: str
