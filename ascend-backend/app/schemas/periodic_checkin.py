"""Weekly and monthly check-in schemas (shared shape, cadence-parameterized)."""

from typing import Any

from pydantic import BaseModel, Field


class PeriodicCheckinOption(BaseModel):
    """Single answer option for a weekly/monthly check-in question."""

    label: str


class PeriodicCheckinQuestion(BaseModel):
    """Normalized weekly/monthly check-in question definition."""

    id: int
    code: str
    label: str
    readiness_component: str
    question: str
    answered: bool = False
    current_answer: str | None = None
    options: list[PeriodicCheckinOption]


class PeriodicCheckinStateResponse(BaseModel):
    """Current-period weekly/monthly check-in screen state."""

    cadence: str
    already_completed_this_period: bool
    period_start: str
    period_end: str
    questions: list[PeriodicCheckinQuestion]
    answered_questions: int
    total_questions: int
    submit_label: str


class PeriodicCheckinAnswerInput(BaseModel):
    """Single submitted weekly/monthly check-in answer."""

    question_id: int
    answer: str


class PeriodicCheckinSubmitRequest(BaseModel):
    """Submit all required weekly/monthly check-in answers together."""

    answers: list[PeriodicCheckinAnswerInput] = Field(min_length=1)


class PeriodicCheckinSubmitResponse(BaseModel):
    """Result of a completed weekly/monthly check-in submission."""

    cadence: str
    component_scores: dict[str, float | None]
    provider_flags: list[dict[str, Any]]
    period_start: str
    period_end: str
