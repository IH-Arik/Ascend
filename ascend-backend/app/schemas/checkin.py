"""Daily check-in schemas."""

from typing import Any

from pydantic import BaseModel, Field


class DailyCheckinOption(BaseModel):
    """Single answer option for a daily check-in question."""

    label: str
    description: str | None = None


class DailyCheckinQuestion(BaseModel):
    """Normalized daily check-in question definition."""

    id: int
    code: str
    label: str
    readiness_component: str
    question: str
    description: str | None = None
    answer_type: str = "single_select"
    scoreable: bool
    flag_only: bool = False
    answered: bool = False
    current_answer: str | None = None
    options: list[DailyCheckinOption]
    follow_up: dict[str, Any] | None = None
    follow_up_required: bool = False
    current_follow_up_answer: str | None = None


class DailyCheckinStateResponse(BaseModel):
    """Day-0 / daily check-in screen state."""

    is_day_zero: bool
    already_completed_today: bool
    day0_daily_checkin_status: str
    current_ops_status: str
    ops_confidence_level: str
    weekly_cadence_start_date: str | None = None
    monthly_cadence_start_date: str | None = None
    policy_version: str
    trace_id: str
    questions: list[DailyCheckinQuestion]
    answered_questions: int
    total_questions: int
    submit_label: str
    footer_note: str = "Your responses are used for readiness support, not evaluation."


class DailyCheckinAnswerInput(BaseModel):
    """Single submitted daily check-in answer."""

    question_id: int
    answer: str
    follow_up_answer: str | None = None


class DailyCheckinSubmitRequest(BaseModel):
    """Submit all required daily check-in answers together."""

    answers: list[DailyCheckinAnswerInput] = Field(min_length=1)


class WeeklyGateResponse(BaseModel):
    """Weekly check-in cadence gate status (informational only)."""

    locked: bool
    cadence_label: str = "Weekly · Tue 0600"
    today: str
    days_until_open: int
    next_open_at: str
    cadence_start_date: str | None
    trace_id: str


class DailyCheckinSubmitResponse(BaseModel):
    """Result of a completed daily check-in submission."""

    is_day_zero: bool
    day0_daily_checkin_status: str
    current_ops_status: str
    ops_confidence_level: str
    current_ops_score: float | None
    current_ops_band: str
    component_scores: dict[str, float | None]
    provider_flags: list[dict[str, Any]]
    weekly_cadence_start_date: str | None
    monthly_cadence_start_date: str | None
    ai_summary: dict[str, Any]
    recommendation: dict[str, Any] | None = None
