"""Equipment and Supply Gap Tracker schemas (DOCX section 8.7)."""

from pydantic import BaseModel, Field

PRIORITIES = ("low", "medium", "high")
GAP_STATUSES = ("open", "ordered", "resolved")


class EquipmentGapCreate(BaseModel):
    """Log a new equipment/supply gap."""

    item: str = Field(min_length=1, max_length=120)
    supply_need: str = Field(min_length=1, max_length=500)
    priority: str = Field(default="medium", pattern="^(" + "|".join(PRIORITIES) + ")$")


class EquipmentGapUpdate(BaseModel):
    """Update an equipment/supply gap's status."""

    status: str = Field(pattern="^(" + "|".join(GAP_STATUSES) + ")$")
    included_in_report: bool | None = None


class EquipmentGapResponse(BaseModel):
    """A single equipment/supply gap."""

    id: str
    item: str
    supply_need: str
    priority: str
    requested_by_name: str | None
    date_identified: str
    status: str
    included_in_report: bool
