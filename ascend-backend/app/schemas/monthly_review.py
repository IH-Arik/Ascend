"""Monthly review schemas.

"Signed off by <provider>" and the immutable/locked-on-publish workflow
shown on the Monthly Review screen require a real provider roster/identity
and a sign-off action, neither of which exist yet. `review_status` is
therefore always "draft" here - a real, on-demand summary of real data,
just never signed or locked. Medical-records content ("1 MRI upload...") is
intentionally left out - that module is out of scope (see docs on medical
records governance).
"""

from typing import Any

from pydantic import BaseModel


class ProviderNote(BaseModel):
    """A recent message from a provider, surfaced as a "note for you"."""

    sender_name: str | None
    sender_role: str
    body: str
    created_at: str


class DailyCheckinRecap(BaseModel):
    """Daily check-in cadence over the review period."""

    days_logged: int
    days_total: int
    cadence_percent: float


class MonthlyReviewResponse(BaseModel):
    """Aggregated monthly review payload."""

    review_status: str
    period_label: str
    period_start: str
    period_end: str
    generated_at: str
    thirty_day_recap: list[dict[str, Any]]
    average_ops_score: float | None
    average_ops_delta: float | None
    daily_checkins: DailyCheckinRecap
    workout_summary: dict[str, Any]
    oft_status: dict[str, Any]
    provider_notes: list[ProviderNote]
