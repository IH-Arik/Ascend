"""My Support Team assignment model.

One record per (operator, pathway). SCS/PT-IM are "locked_on" - assigned
automatically, cannot be disabled (matches "Your SCS and PT/IM are assigned
automatically" on the My Team screen). The 3 optional pathways start
"disabled" and the operator toggles them on/off; every toggle is audit
logged (see app/services/team_service.py).
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


STATUS_LOCKED_ON = "locked_on"
STATUS_ENABLED = "enabled"
STATUS_DISABLED = "disabled"

# Real, added 2026-09-01 - the Chaplain dashboard's "Opt-in confirmation
# audit" showed a real timestamp+status (already backed by this model)
# plus a "Method"/"Witness" pair with nothing behind either. A self-service
# app toggle (`toggle_pathway`) is real and always "app_self_service"; the
# other 3 require a specialist to actually record a real witnessed
# interaction (`record_witnessed_opt_in`).
OPT_IN_METHODS = ("app_self_service", "secure_form_signed", "in_person_verbal", "casual_contact_on_request")
# Real, added 2026-09-01 - the same dashboard's caseload table showed a
# per-airman "Reflection cadence" (Weekly/Bi-weekly/Monthly/Paused) with no
# real field behind it. Distinct from the real daily/weekly/monthly OPS
# check-in cadence - this is the Chaplain's own pacing preference for how
# often they expect a reflection from this specific person, not a system
# cadence.
REFLECTION_CADENCES = ("weekly", "bi_weekly", "monthly", "paused")


class TeamAssignment(Document):
    """A single pathway's assignment/enable-state for one operator."""

    user_id: PydanticObjectId
    pathway_key: str
    provider_user_id: PydanticObjectId | None = None
    status: str = "disabled"
    opt_in_method: str | None = None
    witnessed_by_id: PydanticObjectId | None = None
    reflection_cadence: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "team_assignments"
        indexes = [
            IndexModel([("user_id", 1), ("pathway_key", 1)], unique=True),
        ]
