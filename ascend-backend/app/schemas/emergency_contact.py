"""Per-unit emergency contact directory schemas (Fly Away Kit, Admin-set)."""

from pydantic import BaseModel, Field


class EmergencyContactUpdate(BaseModel):
    """Admin sets a unit's emergency contact directory."""

    scs_on_call_phone: str | None = Field(default=None, max_length=40)
    ptim_clinic_phone: str | None = Field(default=None, max_length=40)
    ptim_clinic_hours: str | None = Field(default=None, max_length=60)
    chaplain_hotline_phone: str | None = Field(default=None, max_length=40)
    family_contact_note: str | None = Field(default=None, max_length=120)


class EmergencyContactResponse(BaseModel):
    """A unit's emergency contact directory."""

    unit_id: str
    scs_on_call_phone: str | None
    ptim_clinic_phone: str | None
    ptim_clinic_hours: str | None
    chaplain_hotline_phone: str | None
    family_contact_note: str | None
    updated_at: str
