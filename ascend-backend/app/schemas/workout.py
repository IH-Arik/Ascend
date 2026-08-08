"""Workout/activity log schemas (DOCX section 9).

`intensity` is RPE (Rate of Perceived Exertion), 1-5, matching the "Log
workout" screen exactly - not a light/moderate/high label.
"""

from datetime import date

from pydantic import BaseModel, Field, model_validator

ACTIVITY_TYPES = ("strength", "cardio", "mobility", "recovery", "other")
COMPLETION_STATUSES = ("completed", "partial", "missed")

# A conservative, deterministic keyword scan (no AI) over workout notes - a
# match sets `reported_limitation` and notifies the assigned SCS, matching
# the DOCX's "notes/limitations" field and "SCS views: ... reported
# limitations" requirement.
LIMITATION_TERMS: tuple[str, ...] = (
    "pain",
    "injury",
    "injured",
    "hurt",
    "sore",
    "strain",
    "sprain",
    "limitation",
)


class WorkoutLogCreate(BaseModel):
    """Log a single workout/activity session."""

    activity_date: date
    activity_type: str = Field(pattern="^(" + "|".join(ACTIVITY_TYPES) + ")$")
    custom_title: str | None = Field(default=None, max_length=60)
    duration_minutes: int = Field(ge=1, le=600)
    intensity: int = Field(ge=1, le=5)
    completion_status: str = Field(default="completed", pattern="^(" + "|".join(COMPLETION_STATUSES) + ")$")
    notes: str | None = Field(default=None, max_length=280)
    session_rating: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def _require_custom_title_for_other(self) -> "WorkoutLogCreate":
        """Require a custom title only when activity_type is "other"."""
        if self.activity_type == "other" and not self.custom_title:
            raise ValueError("custom_title is required when activity_type is 'other'.")
        return self


class WorkoutLogResponse(BaseModel):
    """A single logged workout/activity session."""

    id: str
    activity_date: str
    activity_type: str
    custom_title: str | None
    duration_minutes: int
    intensity: int
    completion_status: str
    notes: str | None
    reported_limitation: bool
    session_rating: int | None


class WorkoutSummaryResponse(BaseModel):
    """Aggregate workout summary over a date range."""

    range_days: int
    total_sessions: int
    completed_sessions: int
    missed_sessions: int
    by_activity_type: dict[str, int]
    total_duration_minutes: int
    recent_adherence_label: str
    current_streak_weeks: int
