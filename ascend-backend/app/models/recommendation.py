"""Recommendation / assigned-action persistence model (DOCX section 4).

Covers two origins of the same underlying concept: an auto-generated
coaching nudge from the rule engine (`assigned_provider_name` is None), and
a provider-assigned plan-link action such as a rehab exercise (has
`assigned_provider_name`/`role`, `instructions`, and `steps`) - matching the
"Assigned action" detail screen.
"""

from datetime import date, datetime, timezone
from typing import Any

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Recommendation(Document):
    """A single traceable readiness recommendation or assigned action for one user."""

    user_id: PydanticObjectId
    readiness_component: str
    severity: str
    score_band: str
    threshold_level: float
    source_component_score: float | None = None
    trigger_reason: str
    signal_label: str
    title: str
    body: str
    provider_action_type: str
    specialist_route: str | None = None
    route_level: str | None = None
    follow_up_timeline: str
    status: str = "active"
    assigned_provider_name: str | None = None
    assigned_provider_role: str | None = None
    due_date: date | None = None
    instructions: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    assigned_by: PydanticObjectId | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "recommendations"
        indexes = [
            IndexModel([("user_id", 1), ("status", 1), ("created_at", -1)]),
        ]
