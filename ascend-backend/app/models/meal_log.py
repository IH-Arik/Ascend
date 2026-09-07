"""Meal log model.

New backend surface, not DOCX-sourced - the old Figma mock's Nutritionist
"Meal consistency & logs" section showed individual meal entries
(time/description/macros) with no real backend model behind them. Built on
explicit user go-ahead so that section can show real logged meals instead
of fabricated ones. `nutrition_signals` (meal_consistency_trend,
hydration_energy_trend, etc. in `provider_dashboard_service`) is a separate,
pre-existing, real signal derived from checkin answers - this model is the
actual per-meal entry data those signals were missing.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack", "pre_workout", "post_workout")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class MealLog(Document):
    """A single real logged meal - time, description, and optional macro breakdown."""

    user_id: PydanticObjectId
    meal_date: datetime  # when the meal was eaten
    meal_type: str  # one of MEAL_TYPES
    description: str = Field(min_length=1, max_length=500)

    calories: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)

    # A Nutritionist can flag an entry for review (skipped meal, low protein, etc.)
    flagged: bool = False
    flag_reason: str | None = None
    logged_by_id: PydanticObjectId  # the operator, or a Nutritionist logging on their behalf
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "meal_logs"
        indexes = [
            IndexModel([("user_id", 1), ("meal_date", -1)]),
            IndexModel([("user_id", 1), ("flagged", 1)]),
        ]
