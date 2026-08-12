"""Report export lifecycle schema."""

from pydantic import BaseModel, Field

from app.models.report_export import LIFECYCLE_STATUSES


class ReportLifecycleUpdate(BaseModel):
    """Explicitly transition a report's real Leadership-facing lifecycle status."""

    lifecycle_status: str = Field(pattern="^(" + "|".join(LIFECYCLE_STATUSES) + ")$")
