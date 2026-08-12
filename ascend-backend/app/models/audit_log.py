"""Append-only audit log model (docs/AUDIT_LOG_RULES.md).

Fields match the docs' "Suggested Audit Fields" list. Records are never
updated or deleted after insert - append-only per the docs' Design Rules.
"""

from datetime import datetime, timezone
from typing import Any

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class AuditLog(Document):
    """A single immutable audit event."""

    event_type: str
    # Optional - a system-generated entry (e.g. the threshold-warning job,
    # `app/core/scheduler.py`) has no real human actor. Every entry created
    # by a real person still has a real `actor_id`; this only widens the
    # type, it never changes existing data.
    actor_id: PydanticObjectId | None = None
    actor_role: str
    target_entity_type: str
    target_entity_id: str
    summary_message: str
    metadata_payload: dict[str, Any] = Field(default_factory=dict)
    outcome_status: str = "success"
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "audit_logs"
        indexes = [
            IndexModel([("actor_id", 1), ("created_at", -1)]),
            IndexModel([("target_entity_type", 1), ("target_entity_id", 1)]),
        ]
