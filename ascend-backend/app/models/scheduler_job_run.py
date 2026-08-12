"""Persistent scheduler job-run history, for a real system-health metric.

Before this, `app/core/scheduler.py`'s daily job only called
`logger.info`/`logger.warning` - job history was ephemeral (lost on
restart/log rotation), so there was no real data source for a "system
health" figure. This model gives the Admin Control Plane Overview screen a
genuine success-rate metric instead of a fabricated number: one row per
real daily run, starting empty and filling in over time.
"""

from datetime import datetime, timezone

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class SchedulerJobRun(Document):
    """A single real execution record of a background scheduler job."""

    job_name: str
    status: str  # "success" | "failed"
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    error_message: str | None = None

    class Settings:
        """Beanie collection settings."""

        name = "scheduler_job_runs"
        indexes = [
            IndexModel([("job_name", 1), ("started_at", -1)]),
        ]
