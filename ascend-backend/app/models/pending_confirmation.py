"""Second-reviewer confirmation queue for destructive admin actions.

Not DOCX-sourced - the Admin/Superadmin "Control plane" Figma screen shows
a two-person-rule workflow (exports and deactivations awaiting a second
reviewer, role changes marked "gated") that has no DOCX requirement behind
it. Built as real new scope per explicit instruction: an admin-level role
change, a provider/admin-account deactivation, or a "restricted"-sensitivity
report export is requested by one Admin/Superadmin and must be approved by
a *different* Admin/Superadmin before it actually takes effect.

`snapshot_before` carries what's needed to `revert` an approved action
(restore a prior role, reactivate a deactivated account) - not available
for `action_type == "export"`, where the approval gate itself is the safety
mechanism (nothing to undo once a CSV has been generated).
"""

from datetime import datetime, timezone
from typing import Any

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class PendingConfirmation(Document):
    """A destructive admin action awaiting a second reviewer's approval."""

    action_type: str  # "role_change" | "deactivation" | "export" | "idmt_handoff"
    status: str = "pending"  # pending | approved | rejected
    requested_by: PydanticObjectId
    requested_at: datetime = Field(default_factory=utc_now)
    # Real, only set for `action_type == "export"` (a Figma "System" screen's
    # "Export approval window: 72h" claim) - `role_change`/`deactivation`
    # have no established real expiry rule, so this stays `None` for them
    # rather than guessing one.
    expires_at: datetime | None = None
    reviewed_by: PydanticObjectId | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    target_entity_type: str
    target_entity_id: str
    target_summary: str
    consequence_summary: str
    # Real, added 2026-08-23 - a Figma "Review Pending Request" modal showed
    # a `SCOPE` field with no backing anywhere (`admin-store.ts` had it
    # hardcoded per row). Computed once at request time from already-real
    # data, same pattern as `target_summary`/`consequence_summary`: the
    # affected user's role + unit for `role_change`/`deactivation`, content
    # category + target role for `idmt_handoff`, sensitivity level +
    # recipient role for `export`. `None` for any confirmation created
    # before this field existed.
    scope_summary: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    snapshot_before: dict[str, Any] = Field(default_factory=dict)
    executed_at: datetime | None = None
    reverted_at: datetime | None = None
    reverted_by: PydanticObjectId | None = None

    class Settings:
        """Beanie collection settings."""

        name = "pending_confirmations"
        indexes = [
            IndexModel([("status", 1), ("requested_at", -1)]),
            IndexModel([("target_entity_type", 1), ("target_entity_id", 1)]),
        ]
