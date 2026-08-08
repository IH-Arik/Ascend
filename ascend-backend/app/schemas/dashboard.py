"""Home dashboard schemas."""

from typing import Any

from pydantic import BaseModel


class CurrentOpsBlock(BaseModel):
    """Current OPS summary card."""

    ops_score: float | None
    ops_band: str
    band_meaning: str
    confidence_level: str
    trend_delta: float | None
    last_updated_at: str | None


class TodaysCheckinBlock(BaseModel):
    """Today's check-in prompt card."""

    already_completed_today: bool
    title: str
    body: str
    cta_label: str | None
    total_questions: int


class DriverTrend(BaseModel):
    """A single readiness component's current score and recent trend."""

    readiness_component: str
    signal_label: str
    current_score: float | None
    stale: bool
    trend_points: list[float]


class SupportPathwayPreview(BaseModel):
    """A support pathway tile shown on the home dashboard."""

    key: str
    label: str
    description: str
    availability_status: str


class UpcomingItem(BaseModel):
    """A single upcoming cadence item."""

    key: str
    title: str
    subtitle: str
    tag: str


class TrendPoint(BaseModel):
    """A single dated OPS score point."""

    date: str
    ops_score: float | None
    ops_band: str
    confidence_level: str


class ComponentTrendSeries(BaseModel):
    """A full dated history for one readiness component."""

    readiness_component: str
    signal_label: str
    points: list[dict[str, Any]]


class DriverOverviewItem(BaseModel):
    """A single driver card on the Trends screen ("Driver overview")."""

    readiness_component: str
    signal_label: str
    current_score: float | None
    weight: float
    has_daily_trend: bool
    trend_points: list[float]
    delta_vs_prior_period: float | None


class OpsHistoryDay(BaseModel):
    """One day's readiness band and dominant driver for the OPS history grid."""

    date: str
    ops_band: str
    dominant_driver: str | None


class PublicAggregateBlock(BaseModel):
    """The unit-level aggregate report CTA, gated by k-anonymity."""

    available: bool
    min_cohort_size: int
    reason: str


class TrendsResponse(BaseModel):
    """Full trend history payload for the Trends screen."""

    range_days: int
    period_label: str
    ops_series: list[TrendPoint]
    component_series: list[ComponentTrendSeries]
    driver_overview: list[DriverOverviewItem]
    ops_history: list[OpsHistoryDay]
    next_windows: list[UpcomingItem]
    public_aggregate: PublicAggregateBlock
    last_updated_label: str | None


class DriverInfluence(BaseModel):
    """A single explainability signal shown under "What influences this"."""

    key: str
    title: str
    detail: str


class DriverDetailResponse(BaseModel):
    """Detail payload for a single readiness driver (Driver Detail screen)."""

    readiness_component: str
    signal_label: str
    current_score: float | None
    score_band: str
    last_updated_at: str | None
    trend_points: list[dict[str, Any]]
    trend_direction: str
    delta_7d: float | None
    delta_30d: float | None
    try_this: list[str]
    influences: list[DriverInfluence]
    support_cta_label: str
    support_route: str | None


class UnitAggregateReportResponse(BaseModel):
    """Unit-level aggregate readiness report, k-anonymity gated.

    Returned only when at least `min_cohort_size` users share a unit;
    otherwise no aggregate is computed at all (not even a partial one).
    """

    available: bool
    unit_id: str | None
    cohort_size: int
    min_cohort_size: int
    reason: str | None
    average_ops_score: float | None = None
    band_distribution: dict[str, int] | None = None
    component_averages: dict[str, float | None] | None = None


class HomeDashboardResponse(BaseModel):
    """Aggregated payload for the Home dashboard screen."""

    greeting: str
    subtitle: str
    date_label: str
    current_ops: CurrentOpsBlock
    todays_checkin: TodaysCheckinBlock
    driver_trends: list[DriverTrend]
    component_scores: dict[str, float | None]
    today_for_you: dict[str, Any] | None
    support_preview: list[SupportPathwayPreview]
    upcoming: list[UpcomingItem]
    last_updated_label: str | None
