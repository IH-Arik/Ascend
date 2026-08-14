"""Medical record upload schemas (DOCX section 8.8)."""

from pydantic import BaseModel, Field

DOCUMENT_TYPES = ("labs", "imaging", "specialist", "dme", "other")
MIN_ACCESS_REASON_LENGTH = 12


class MedicalRecordResponse(BaseModel):
    """A single medical record's list-view fields."""

    id: str
    document_type: str
    file_name: str
    file_type: str
    file_size_bytes: int
    status: str
    access_reason: str
    uploaded_at: str
    reviewed_at: str | None


class AccessEventResponse(BaseModel):
    """A single access-reason/action log entry."""

    actor_name: str
    actor_role: str
    action: str
    note: str
    created_at: str


class MedicalRecordDetailResponse(BaseModel):
    """A single medical record's full detail view."""

    id: str
    document_type: str
    file_name: str
    file_type: str
    file_size_bytes: int
    status: str
    access_reason: str
    uploaded_by_name: str | None
    uploaded_at: str
    reviewed_by_name: str | None
    reviewed_at: str | None
    access_log: list[AccessEventResponse]


class RecordReviewRequest(BaseModel):
    """PT/IM marks an uploaded record reviewed - approved or denied."""

    note: str = Field(min_length=1, max_length=500)
    approve: bool = True


class AccessLevelUpdateRequest(BaseModel):
    """Admin narrows/sets a specific record's real approved-access role list."""

    approved_access_level: list[str] = Field(min_length=1)


REASON_CATEGORIES = ("routine", "escalation", "follow_up", "audit", "other")


class RevealFieldRequest(BaseModel):
    """A non-clinical viewer's reason-required, one-time reveal of a masked field."""

    field_name: str
    reason: str = Field(min_length=MIN_ACCESS_REASON_LENGTH, max_length=500)
    reason_category: str = Field(pattern="^(" + "|".join(REASON_CATEGORIES) + ")$")
