"""Assessment request and response schemas."""

from datetime import datetime

from pydantic import BaseModel

from app.models.behavior import BehaviorType


class SubmittedAnswerRequest(BaseModel):
    """Raw answer submitted by the client."""

    question_id: str
    answer: str


class CheckInCreate(BaseModel):
    """Payload for submitting the fixed assessment."""

    answers: list[SubmittedAnswerRequest]


class AnswerRead(BaseModel):
    """Serialized normalized answer payload."""

    question_id: str
    answer_text: str
    numeric_value: float
    driver: str


class CheckInRead(BaseModel):
    """Serialized check-in response."""

    id: str
    user_id: str
    answers: list[AnswerRead]
    submitted_at: datetime


class DailyCheckInQuestionRead(BaseModel):
    """Serialized daily check-in question payload."""

    id: str
    text: str
    driver: str
    response_type: str
    options: list[str]
    weight: float
    order: int


class DailyCheckInCreate(BaseModel):
    """Payload for submitting the daily check-in."""

    answers: list[SubmittedAnswerRequest]
    behaviors: list[BehaviorType] = []


class DailyCheckInRead(BaseModel):
    """Serialized daily check-in response."""

    id: str
    user_id: str
    answers: list[AnswerRead]
    submitted_at: datetime


class WeeklyCheckInQuestionRead(BaseModel):
    """Serialized weekly check-in question payload."""

    id: str
    text: str
    driver: str
    response_type: str
    options: list[str]
    weight: float
    order: int


class WeeklyCheckInCreate(BaseModel):
    """Payload for submitting the weekly check-in."""

    answers: list[SubmittedAnswerRequest]
    behaviors: list[BehaviorType] = []


class WeeklyCheckInRead(BaseModel):
    """Serialized weekly check-in response."""

    id: str
    user_id: str
    answers: list[AnswerRead]
    submitted_at: datetime


class WeeklyCheckInStatusRead(BaseModel):
    """Serialized weekly availability status."""

    should_show_weekly_checkin: bool
    eligible_after_daily_streak_days: int
    current_daily_streak_days: int
    weekly_checkin_completed_this_week: bool
    last_weekly_checkin_date: datetime | None


class MonthlyCheckInQuestionRead(BaseModel):
    """Serialized monthly check-in question payload."""

    id: str
    text: str
    driver: str
    response_type: str
    options: list[str]
    weight: float
    order: int


class MonthlyCheckInCreate(BaseModel):
    """Payload for submitting the monthly check-in."""

    answers: list[SubmittedAnswerRequest]
    behaviors: list[BehaviorType] = []


class MonthlyCheckInRead(BaseModel):
    """Serialized monthly check-in response."""

    id: str
    user_id: str
    answers: list[AnswerRead]
    submitted_at: datetime


class MonthlyCheckInStatusRead(BaseModel):
    """Serialized monthly availability status."""

    should_show_monthly_checkin: bool
    eligible_after_daily_streak_days: int
    completed_daily_checkin_days: int
    current_daily_streak_days: int
    monthly_checkin_completed_this_month: bool
    last_monthly_checkin_date: datetime | None


class AssessmentStatusRead(BaseModel):
    """Eligibility status for the 90-day baseline assessment."""

    can_submit_assessment: bool
    is_initial_assessment: bool
    last_assessment_date: str | None
    next_eligible_date: str | None
    days_remaining: int
    lock_message: str | None
