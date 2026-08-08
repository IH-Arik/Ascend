"""Onboarding and first-use schemas."""

from typing import Any

from pydantic import BaseModel, Field


class FirstUseStatusResponse(BaseModel):
    """Current first-use state for the authenticated user."""

    onboarding_status: str
    onboarding_step: str
    onboarding_completed: bool
    day0_daily_checkin_status: str
    current_ops_status: str
    ops_confidence_level: str
    next_route: str
    dashboard_locked: bool


class OnboardingIntroResponse(BaseModel):
    """Payload for the welcome and before-we-begin screens."""

    screen_code: str
    screen_title: str
    step_title: str
    progress_label: str
    operator_label: str
    welcome_name: str
    intro_body: str
    cta_label: str
    privacy_summary: str
    consent_required_label: str
    consent_required_description: str
    optional_opt_in_label: str
    optional_opt_in_description: str
    medical_record_notice: str
    policy_version: str
    trace_id: str
    opsec_notice_text: str | None = None


class ConsentSubmitRequest(BaseModel):
    """Capture required and optional onboarding consent fields."""

    data_use_consent: bool
    wellness_recommendations_opt_in: bool = False
    policy_version: str = Field(min_length=3, max_length=80)


class StepProgressRequest(BaseModel):
    """Track current onboarding progress."""

    onboarding_step: str = Field(min_length=2, max_length=80)
    onboarding_status: str = Field(default="in_progress", min_length=2, max_length=40)


class OnboardingQuestionOption(BaseModel):
    """Single answer option in the onboarding question bank."""

    label: str
    score: int | None = None
    description: str | None = None
    disabled: bool = False
    value: bool | str | None = None


class OnboardingQuestionResponse(BaseModel):
    """Normalized onboarding question definition."""

    id: int
    code: str
    question_number: int
    question_total: int
    category: str
    readiness_component: str
    question: str
    description: str
    answer_type: str
    scoreable: bool
    reverse_scored: bool = False
    estimated_time_label: str
    submit_label: str
    footer_note: str
    support_note_variant: str
    follow_up_required: bool = False
    answered: bool = False
    current_answer: str | list[str] | None = None
    current_follow_up_answer: str | list[str] | dict[str, Any] | None = None
    options: list[OnboardingQuestionOption]
    routing_text: str
    routing_trigger: list[str] = Field(default_factory=list)
    provider_route: str | None = None
    follow_up: dict[str, Any] | None = None
    ai_tags: list[str] = Field(default_factory=list)


class OnboardingAnswerSubmission(BaseModel):
    """Submit one onboarding answer or follow-up response."""

    question_id: int
    answer: str | list[str] | dict[str, Any]
    follow_up_answer: str | list[str] | dict[str, Any] | None = None


class BaselineFinalizeResponse(BaseModel):
    """Return the computed onboarding baseline summary."""

    onboarding_status: str
    onboarding_step: str
    onboarding_completed: bool
    baseline_ops_score: float | None
    baseline_band: str
    confidence: str
    component_scores: dict[str, float | None]
    provider_flags: list[dict[str, Any]]
    follow_ups: list[dict[str, Any]]
    ai_payload: dict[str, Any]
    ai_summary: dict[str, Any]
