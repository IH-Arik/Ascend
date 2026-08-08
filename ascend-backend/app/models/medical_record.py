"""Medical record upload model (DOCX section 8.8, Medical Records Upload and
Health History Support).

DOCX: "Ascend must not become the official medical record ... unless
expressly authorized by the Government" - these are controlled copies for
performance support, never the system of record. `access_reason` is
required on every upload and every subsequent view is logged (see
`MedicalRecordAccessEvent`), per the DOCX's audit-logging requirement for
every upload/view/download/export.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class MedicalRecord(Document):
    """A single uploaded medical record (controlled copy, not a system of record)."""

    user_id: PydanticObjectId
    document_type: str
    file_name: str
    file_type: str
    file_size_bytes: int
    storage_path: str
    access_reason: str
    status: str = "pending"
    uploaded_by: PydanticObjectId
    uploaded_at: datetime = Field(default_factory=utc_now)
    reviewed_by: PydanticObjectId | None = None
    reviewed_at: datetime | None = None

    class Settings:
        """Beanie collection settings."""

        name = "medical_records"
        indexes = [
            IndexModel([("user_id", 1), ("uploaded_at", -1)]),
        ]


class MedicalRecordAccessEvent(Document):
    """An append-only access-reason/action log entry for one medical record."""

    record_id: PydanticObjectId
    actor_id: PydanticObjectId | None = None
    actor_role: str
    action: str
    note: str
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "medical_record_access_events"
        indexes = [
            IndexModel([("record_id", 1), ("created_at", 1)]),
        ]
