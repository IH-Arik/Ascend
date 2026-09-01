"""Specialist provider session schedule (Mental Performance/Nutritionist/Chaplain).

Not DOCX-sourced (the Figma MP and Nutritionist dashboards each showed
their own "Today's sessions"/"Consult queue" widget - time, individual/
group, topic, status - with no backend concept anywhere). Real new scope,
explicit user go-ahead: a real, scheduled session (individual or group) a
specialist provider leads, distinct from a `SupportRequest` (the user's
initial ask, not a scheduled meeting) and from `SpecialistNote` (the
record of what happened in a session, not the schedule of one). Mirrors
`PTSession`'s real attendee/capacity pattern.

Started as MP-only (`MPSession`, 2026-09-01) and was generalized the same
day, before any frontend wiring existed, once the Nutritionist audit hit
the identical "consult scheduling" gap - one shared model across all 3
optional specialist pathways rather than 3 near-duplicates, matching how
`SpecialistNote` is already a single shared model.
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class SpecialistSession(Document):
    """A single scheduled specialist session, individual or group."""

    provider_id: PydanticObjectId
    provider_role: str
    session_date: date
    start_time: str
    session_type: str = "individual"  # "individual" | "group"
    # Individual: exactly one id. Group: the roster. Same real list-based
    # attendee pattern as `PTSession.attendee_user_ids`.
    attendee_user_ids: list[PydanticObjectId] = Field(default_factory=list)
    group_label: str | None = None
    topic: str | None = None
    capacity: int | None = None
    status: str = "scheduled"  # scheduled | completed | escalated | cancelled | no_show
    created_by: PydanticObjectId
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "specialist_sessions"
        indexes = [
            IndexModel([("provider_id", 1), ("session_date", 1)]),
        ]
