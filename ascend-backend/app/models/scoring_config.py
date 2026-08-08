"""Admin-configurable OPS scoring weights/band thresholds (DOCX Data
Dictionary: "Scoring Configuration | config_id, effective_date,
physical_weight, sleep_weight, mental_weight... | Admin can update
thresholds without code changes.").

Versioned and effective-dated, never overwritten in place - the active
config is the most recent one whose `effective_date` is today or earlier,
so a scheduled future change can be queued ahead of time without affecting
current scoring.
"""

from datetime import date, datetime, timezone
from typing import Any

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ScoringConfig(Document):
    """One versioned, effective-dated OPS scoring configuration."""

    effective_date: date = Field(default_factory=date.today)
    physical_weight: float = 0.25
    sleep_weight: float = 0.20
    mental_weight: float = 0.20
    nutritional_weight: float = 0.20
    spiritual_weight: float = 0.15
    band_thresholds: dict[str, float] = Field(
        default_factory=lambda: {
            "Ready": 85.0,
            "Monitor": 70.0,
            "Caution": 55.0,
            "Action Needed": 40.0,
        }
    )
    created_by: PydanticObjectId | None = None
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "scoring_configs"
        indexes = [
            IndexModel([("effective_date", -1)]),
        ]

    def as_weights(self) -> dict[str, float]:
        """Return this config's weights in the shape `calculate_ops` expects."""
        return {
            "Physical Readiness": self.physical_weight,
            "Sleep Readiness": self.sleep_weight,
            "Mental Readiness": self.mental_weight,
            "Nutritional Readiness": self.nutritional_weight,
            "Spiritual Readiness": self.spiritual_weight,
        }
