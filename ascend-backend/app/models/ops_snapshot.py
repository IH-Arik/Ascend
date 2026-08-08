"""OPS snapshot persistence model (one per check-in, powers dashboard trend history)."""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class OpsSnapshot(Document):
    """Persist a computed OPS/component snapshot for driver-trend and dashboard history."""

    user_id: PydanticObjectId
    cadence: str = "daily"
    snapshot_date: date
    ops_score: float | None = None
    ops_band: str
    confidence_level: str
    component_scores: dict[str, float | None] = Field(default_factory=dict)
    stale_components: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "ops_snapshots"
        indexes = [
            IndexModel([("user_id", 1), ("snapshot_date", 1)], unique=True),
            IndexModel([("user_id", 1), ("created_at", -1)]),
        ]
