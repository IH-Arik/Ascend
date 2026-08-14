"""Reconditioning plan model (DOCX: "Joint PT/IM-SCS Coordination" - reconditioning
assignment/monitoring; referenced on the Fly Away Kit "Rehab status" card).

One active plan per user at a time. PT/IM and SCS both author/update it per
the DOCX's joint-coordination model for reconditioning; Admin can as well.

DOCX Section 8.4 (line 752) names a real `Injury/Recovery` record shape:
`injury_id, user_id, status, limitation_flag, return_to_performance_status,
rehab_strategy_summary, ptim_follow_up_date, scs_coordination_status`. This
model already covers most of it under different names - `phase` is the real
`status`, `ptim_clearance_status` is the real `return_to_performance_status`,
`next_review_date` is the real `ptim_follow_up_date` - so this file *is* that
DOCX record, not a separate one. `limitation_flag`, `rehab_strategy_summary`,
and `scs_coordination_status` (added 2026-08-13) close the remaining real gap.
`severity_level`/`injury_reported_on` (also added 2026-08-13) are net-new,
explicit user go-ahead, not DOCX-sourced - operational severity/duration
tracking, not a clinical diagnosis (the DOCX is explicit that OPS/this app is
"not a diagnosis... or substitute for PT/IM judgment").
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ReconditioningPlan(Document):
    """A single operator's active reconditioning/rehab status."""

    user_id: PydanticObjectId
    phase: str = "active"
    phase_started_on: date = Field(default_factory=date.today)
    sessions_completed: int = 0
    sessions_total: int = 0
    cadence_note: str | None = None
    injury_flags: list[str] = Field(default_factory=list)
    ptim_clearance_status: str = "pending_review"
    next_review_date: date | None = None
    limitation_flag: bool = False
    rehab_strategy_summary: str | None = None
    scs_coordination_status: str = "not_required"
    # Net-new (2026-08-13, not DOCX-sourced - see module docstring).
    severity_level: str | None = None
    injury_reported_on: date | None = None
    updated_by: PydanticObjectId | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "reconditioning_plans"
        indexes = [
            IndexModel([("user_id", 1)], unique=True),
        ]
