"""IDMT documentation handoff schemas (DOCX Section 8.5)."""

from pydantic import BaseModel, Field

from app.models.idmt_handoff import EXPORT_FORMATS, EXPORT_TYPES


class IdmtHandoffCreateRequest(BaseModel):
    """PT/IM or Admin prepares a real documentation handoff for IDMT."""

    user_id: str
    export_type: str = Field(pattern="^(" + "|".join(EXPORT_TYPES) + ")$")
    export_format: str = Field(pattern="^(" + "|".join(EXPORT_FORMATS) + ")$")


class IdmtHandoffResponse(BaseModel):
    """A single IDMT documentation handoff's transport-safe fields."""

    id: str
    user_id: str
    user_name: str | None
    export_type: str
    content_category: str
    export_format: str
    prepared_by_name: str | None
    recipient_role: str
    status: str
    prepared_date: str
    transmitted_date: str | None
    acknowledgement_status: str
    acknowledged_by_name: str | None
    acknowledged_at: str | None
