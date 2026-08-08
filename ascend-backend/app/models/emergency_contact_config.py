"""Per-unit emergency contact directory (Fly Away Kit screen).

Admin-set only. Never fabricated - every field defaults to null/empty and
stays that way until an Admin actually enters a real number, so the Fly
Away Kit correctly shows "not yet configured" rather than a fake phone
number.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class EmergencyContactConfig(Document):
    """One unit's emergency contact directory for the Fly Away Kit."""

    unit_id: str
    scs_on_call_phone: str | None = None
    ptim_clinic_phone: str | None = None
    ptim_clinic_hours: str | None = None
    chaplain_hotline_phone: str | None = None
    family_contact_note: str | None = None
    updated_by: PydanticObjectId | None = None
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "emergency_contact_configs"
        indexes = [
            IndexModel([("unit_id", 1)], unique=True),
        ]
