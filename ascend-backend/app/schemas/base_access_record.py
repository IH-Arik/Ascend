"""Base access / badge / pass schemas (DOCX Section 14)."""

from datetime import date

from pydantic import BaseModel, Field

from app.models.base_access_record import APPROVAL_STATUSES


class BaseAccessRecordUpsert(BaseModel):
    """Admin records or updates one staff member's base access / badge / pass item."""

    request_date: date
    approval_status: str = Field(default="pending", pattern="^(" + "|".join(APPROVAL_STATUSES) + ")$")
    expiration_date: date | None = None
    return_required: bool = True
    returned_date: date | None = None


class BaseAccessRecordResponse(BaseModel):
    """A single staff member's base access / badge / pass item."""

    id: str
    user_id: str
    user_name: str | None
    request_date: str
    approval_status: str
    expiration_date: str | None
    return_required: bool
    returned_date: str | None
    is_expired: bool
    updated_at: str
