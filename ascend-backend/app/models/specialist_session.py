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
from pydantic import BaseModel, Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ChecklistItem(BaseModel):
    """One real, provider-authored prep item on a session - not auto-populated from
    other signals (the old Figma mock's checklist items each implied a live status
    pull, e.g. "Hydration adherence 67%", with no real backing for that kind of
    per-item auto-status - so this is deliberately a plain label + a manual
    done/not-done a Nutritionist/MP/Chaplain checks off themselves)."""

    label: str
    done: bool = False


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
    # scheduled | in_progress | completed | escalated | cancelled | no_show
    status: str = "scheduled"
    # Real, provider-authored prep checklist - see `ChecklistItem`.
    prep_checklist: list[ChecklistItem] = Field(default_factory=list)
    # Real session-duration tracking - set only by the actual `start`/`complete`
    # actions below, never backfilled. A session completed without ever being
    # started (e.g. logged after the fact) has no duration, by design - it is
    # excluded from `get_queue_summary`'s average, not counted as 0 minutes.
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_by: PydanticObjectId
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "specialist_sessions"
        indexes = [
            IndexModel([("provider_id", 1), ("session_date", 1)]),
        ]
