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


# DOCX (Developer Acceptance Rules for Scoring): "Every provider-facing plan
# link must state whether it is an SCS recommendation, PT/IM review item,
# joint coordination item, specialist routing item, or user-only
# recommendation." A real, constrained field for that 5-way split - distinct
# from `provider_action_type` (routing-rule-table vocabulary) and
# `specialist_route` (dashboard-queue filter), which already carry other
# meanings and shouldn't be overloaded.
PLAN_LINK_CATEGORIES = (
    "scs_recommendation",
    "ptim_review_item",
    "joint_coordination_item",
    "specialist_routing_item",
    "user_only_recommendation",
)

# Not DOCX-sourced - the ascend-admin frontend's PT/IM "SCS" tab and SCS
# page both show a "Send to PT/IM" sign-off workflow with its own state,
# distinct from a recommendation's ordinary status. Only ever moves past
# "not_required" for a `joint_coordination_item` (see
# `RecommendationService.send_for_signoff`/`sign_off`).
COORDINATION_SIGNOFF_STATUSES = ("not_required", "pending_signoff", "signed_off")


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
    plan_link_category: str | None = None
    coordination_signoff_status: str = "not_required"
    signed_off_by: PydanticObjectId | None = None
    signed_off_at: datetime | None = None
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
