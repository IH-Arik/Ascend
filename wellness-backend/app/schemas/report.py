"""Performance report response schemas."""

from pydantic import BaseModel


class ReportFilterOptionRead(BaseModel):
    """Selectable filter option for the report view."""

    label: str
    value: str | int


class ReportSummaryRead(BaseModel):
    """OPS summary card payload."""

    overall_score: float
    status: str
    percentage_change: float
    progress_value: float


class ReportTrendPointRead(BaseModel):
    """OPS trend point payload."""

    label: str
    value: float
    is_current: bool = False


class DriverTrendRead(BaseModel):
    """Driver trend card payload."""

    key: str
    label: str
    current_score: float
    delta: float
    delta_label: str
    color: str
    sparkline: list[float]


class BehaviorTrendRead(BaseModel):
    """Behavior trend payload."""

    key: str
    label: str
    status: str
    bars: list[float]
    color_scale: list[str]


class ReportFiltersRead(BaseModel):
    """Available report filter options."""

    weeks: list[ReportFilterOptionRead]
    months: list[ReportFilterOptionRead]
    years: list[ReportFilterOptionRead]
    selected_week: str
    selected_month: int
    selected_year: int


class PerformanceReportRead(BaseModel):
    """Full performance report payload."""

    filters: ReportFiltersRead
    ops_summary: ReportSummaryRead
    ops_trend: list[ReportTrendPointRead]
    driver_trends: list[DriverTrendRead]
    behavior_trends: list[BehaviorTrendRead]
    performance_summary: str
