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
    # "pending" | "reviewed_approved" | "reviewed_denied" | "quarantined"
    status: str = "pending"
    uploaded_by: PydanticObjectId
    uploaded_at: datetime = Field(default_factory=utc_now)
    reviewed_by: PydanticObjectId | None = None
    reviewed_at: datetime | None = None
    # DOCX line 147/211 names "retention status"/"disposition status" as a
    # required real field for uploaded medical records - not implemented
    # until now. `+180 days` from upload is our own reasonable default
    # (DOCX doesn't specify a cadence), same pairing style as
    # `User.access_expires_at`.
    access_expires_at: datetime | None = None
    # Remaining DOCX line 147 fields, closed 2026-08-10. "routine" |
    # "sensitive" | "restricted" - our own real vocabulary (`ReportExport`'s
    # "controlled"/"restricted"/"aggregate" doesn't fit records).
    sensitivity_level: str = "controlled"
    # Real - "self_upload" is the only real path a record enters this
    # system through today; the field exists so a future authorized-
    # transfer source has somewhere to go, not fabricating a second source.
    source: str = "self_upload"
    # Real - uploading a record *is* the consent action today (no separate
    # medical-record consent-withdrawal flow exists, unlike the Chaplain
    # pathway's real toggle).
    consent_status: str = "granted"
    # Real per-record override of who may view/review this specific record
    # - defaults to today's hardcoded `VIEW_ALLOWED_ROLES`
    # (`app/services/medical_record_service.py`) so nothing changes unless
    # an admin narrows it for one record.
    approved_access_level: list[str] = Field(default_factory=list)

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
