"""Macro target model.

New backend surface, not DOCX-sourced - the old Figma mock's Nutritionist
"Macro distribution · cohort" widget compared logged macros against
"prescribed targets" with no real target concept behind it. Built on
explicit user go-ahead so a Nutritionist can set a real per-operator
carbs/protein/fat percentage target, and the cohort widget can honestly
compare real logged meals (`app/models/meal_log.py`) against it.

Real history added 2026-09-07 - the mock's "Nutrition Action history"
widget showed multiple real-shaped entries (a date range, active/closed
status, a target, a computed adherence %) with none of it backed. Setting
a new target now closes the prior one (`status`/`ended_at`) instead of
overwriting it in place, so a real, non-fabricated history accumulates -
`title` is a real, provider-authored short label (same pattern as
`SpecialistNote.title`), and adherence is computed on read from real
`MealLog` entries in each target's real active window, never stored as a
guessed number.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

MACRO_TARGET_STATUSES = ("active", "closed")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class MacroTarget(Document):
    """One real, dated macro-split target for one operator, set by their Nutritionist.

    Real history: at most one `status="active"` record per user at a time -
    `MacroTargetService.set_target` closes the current active record
    (`status="closed"`, `ended_at` stamped) before inserting the new one,
    rather than mutating the old record in place.
    """

    user_id: PydanticObjectId
    title: str = Field(min_length=1, max_length=120)
    carbs_pct: float = Field(ge=0, le=100)
    protein_pct: float = Field(ge=0, le=100)
    fat_pct: float = Field(ge=0, le=100)
    status: str = "active"
    set_by_id: PydanticObjectId
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "macro_targets"
        indexes = [
            IndexModel([("user_id", 1), ("status", 1)]),
        ]
