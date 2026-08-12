"""Leadership "Briefings" executive-briefing composer (2026-08-10).

Not DOCX-sourced (a Figma Leadership screen triggered this - the last of 5
Leadership workspace surfaces). Real section data is composed from
already-real aggregates (`LeadershipAggregateService`, `OFTService`, real
`AuditLog(threshold_warning)` severity, real `LeadershipAnnotation`
entries); `generated_content` is real natural-language prose from
`AIInsightsService.generate_briefing_section_narrative` (real Claude call,
real deterministic stub fallback - see that method's docstring).

While `status == "draft"`, `generated_content` is live-regenerated from
current real data on every fetch (`BriefingService.get`) - matches the
screenshot's "Live" preview label. `send()` freezes it at that moment;
a sent briefing's content never silently changes afterward even if the
underlying real data does.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Briefing(Document):
    """A single executive briefing document."""

    title: str
    template_key: str | None = None
    outline: list[dict] = Field(default_factory=list)
    generated_content: dict[str, str] = Field(default_factory=dict)
    status: str = "draft"
    created_by: PydanticObjectId
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    sent_at: datetime | None = None

    class Settings:
        """Beanie collection settings."""

        name = "briefings"
        indexes = [
            IndexModel([("created_by", 1), ("created_at", -1)]),
        ]
