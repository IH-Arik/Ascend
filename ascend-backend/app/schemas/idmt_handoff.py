"""IDMT documentation handoff schemas (DOCX Section 8.5)."""

from pydantic import BaseModel, Field

from app.models.idmt_handoff import EXPORT_FORMATS, EXPORT_TYPES


class IdmtHandoffCreateRequest(BaseModel):
    """PT/IM or Admin prepares a real documentation handoff for IDMT."""

    user_id: str
    export_type: str = Field(pattern="^(" + "|".join(EXPORT_TYPES) + ")$")
    export_format: str = Field(pattern="^(" + "|".join(EXPORT_FORMATS) + ")$")


class IdmtHandoffBatchCreateRequest(BaseModel):
    """PT/IM or Admin prepares one real handoff per user in a cohort.

    Not a new handoff shape - each user still gets their own real,
    individually-approved `IdmtHandoff` (DOCX Section 8.5's data
    dictionary defines the entity per-user). This just lets one call
    create several at once, capped at 50.
    """

    user_ids: list[str] = Field(min_length=1, max_length=50)
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
