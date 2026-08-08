"""Dashboard response schemas."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class UserSummaryRead(BaseModel):
    """Serialized user summary for the home dashboard."""

    name: str
    greeting_message: str
    profile_image: str | None = None


class PerformanceCardRead(BaseModel):
    """Serialized overall performance card."""

    overall_score: float
    score_label: str
    percentage_change: float
    summary_text: str


class DimensionCardRead(BaseModel):
    """Serialized dimension breakdown card."""

    key: Literal["PC", "MR", "MC", "PA", "RC"]
    label: str
    score: float
    condition: str
    description: str
    status_tag: str


class RadarChartPointRead(BaseModel):
    """Chart-ready radar point."""

    key: Literal["PC", "MR", "MC", "PA", "RC"]
    label: str
    score: float


class ProgressPointRead(BaseModel):
    """Chart-ready progress point for a day."""

    day_label: str
    score_value: float | None


class RecommendationRead(BaseModel):
    """Recommendation card."""

    title: str
    description: str
    based_on_dimension: Literal["PC", "MR", "MC", "PA", "RC"]


class StreakRead(BaseModel):
    """Behavior streak card."""

    type: Literal["sleep", "movement", "recovery", "reflection"]
    current_days: int
    status: str


class DailyCheckinStatusRead(BaseModel):
    """Daily check-in status payload."""

    should_show_daily_checkin: bool
    last_checkin_date: date | None
    daily_checkin_completed_today: bool


class DashboardIndicatorRead(BaseModel):
    """Leadership indicator tile payload."""

    key: str
    label: str
    value: str
    status: str
    meta: dict[str, object]


class BurnoutSignalRead(BaseModel):
    """Triggered burnout signal payload."""

    key: str
    label: str
    value: float | None
    threshold: str


class BurnoutAlertRead(BaseModel):
    """Leadership alert card payload."""

    is_active: bool
    level: str
    signals_in_risk: int
    total_signals: int
    triggered_signals: list[BurnoutSignalRead]
    recommended_actions_preview: list[str]
    recommended_actions_all: list[str]
    trend: str
    consecutive_elevated_days: int
    escalated: bool
    escalation_target: str | None = None
    history: list[dict[str, object]]


class TeamActionLogCreate(BaseModel):
    """Payload for logging a leader action."""

    action: str = Field(min_length=2, max_length=160)
    risk_key: Literal[
        "recovery_deficit",
        "high_stress",
        "fatigue",
        "workload_strain",
        "morale_decline",
        "other",
    ] = "other"
    note: str | None = Field(default=None, max_length=300)
    selected_from_recommended: bool = False
    department: str | None = None
    team: str | None = None


class TeamActionLogRead(BaseModel):
    """Serialized leader action log entry."""

    id: str
    risk_key: str
    action: str
    note: str | None = None
    selected_from_recommended: bool
    created_at: datetime
    department: str | None = None
    team: str | None = None


class LeaderSettingsProfileUpdate(BaseModel):
    """Payload for leader settings profile section updates."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    role: str | None = Field(default=None, min_length=1, max_length=120)
    contact_number: str | None = Field(default=None, max_length=60)
    employee_id: str | None = Field(default=None, max_length=60)
    profile_image_url: str | None = Field(default=None, max_length=500)


class LeaderSettingsCompanyUpdate(BaseModel):
    """Payload for leader settings company section updates."""

    company_name: str | None = Field(default=None, min_length=1, max_length=160)
    company_address: str | None = Field(default=None, max_length=300)
    company_logo_url: str | None = Field(default=None, max_length=500)


class LeaderSettingsScopeUpdate(BaseModel):
    """Payload for leader settings scope section updates."""

    department: str | None = Field(default=None, min_length=1, max_length=120)
    team: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, min_length=1, max_length=120)


class SuperadminUserUpdate(BaseModel):
    """Payload for superadmin user management updates."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, min_length=1, max_length=120)
    organization_name: str | None = Field(default=None, min_length=1, max_length=160)


class SuperadminLegalContentUpdate(BaseModel):
    """Payload for superadmin-editable legal/info content."""

    title: str | None = Field(default=None, min_length=1, max_length=160)
    content: str = Field(min_length=1)
    image_url: str | None = Field(default=None, max_length=500)


class SuperadminFAQCreate(BaseModel):
    """Payload for superadmin FAQ creation."""

    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1)
    order: int = 0


class SuperadminFAQUpdate(BaseModel):
    """Payload for superadmin FAQ updates."""

    question: str | None = Field(default=None, min_length=1, max_length=500)
    answer: str | None = Field(default=None, min_length=1)
    order: int | None = None


class HomeDashboardResponse(BaseModel):
    """Full home dashboard payload."""

    user_summary: UserSummaryRead
    overall_performance: PerformanceCardRead
    dimension_breakdown: list[DimensionCardRead]
    radar_chart_data: list[RadarChartPointRead]
    last_7_days_progress: list[ProgressPointRead]
    personalized_improvement_plan: list[RecommendationRead]
    leader_action_plan: list[RecommendationRead]
    behavior_streaks: list[StreakRead]
    daily_checkin_status: DailyCheckinStatusRead
    dashboard_indicators: list[DashboardIndicatorRead]
    burnout_alert: BurnoutAlertRead
