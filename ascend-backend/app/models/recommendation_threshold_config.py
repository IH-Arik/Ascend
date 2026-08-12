"""Admin-configurable recommendation trigger thresholds (DOCX section 4,
Recommendation Engine - "Admin can update thresholds without code changes"
applies to the Provider Trigger Rules the same way it applies to OPS
scoring, see `app/models/scoring_config.py`).

Versioned and effective-dated, mirroring `ScoringConfig` exactly - the
active config is the most recent one whose `effective_date` is today or
earlier, so a scheduled future change can be queued ahead of time.
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class RecommendationThresholdConfig(Document):
    """One versioned, effective-dated recommendation trigger configuration."""

    effective_date: date = Field(default_factory=date.today)
    # DOCX baseline defaults - identical to `app.core.recommendation_rules`'s
    # hardcoded HIGH_THRESHOLD/MODERATE_THRESHOLD, which remain the real
    # fallback when no Admin config has been created yet.
    high_threshold: float = 55.0
    moderate_threshold: float = 70.0
    created_by: PydanticObjectId | None = None
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "recommendation_threshold_configs"
        indexes = [
            IndexModel([("effective_date", -1)]),
        ]
