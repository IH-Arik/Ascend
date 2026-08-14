"""IDMT documentation handoff model.

DOCX Section 8.5 ("Software Tracking System and IDMT Documentation
Support") data dictionary defines this field-for-field: `handoff_id,
user_id, export_type, prepared_by, recipient_role, prepared_date,
transmitted_date, acknowledgement_status`. The DOCX also requires: track
prepared -> transmitted -> acknowledged as distinct real states; maintain a
handoff log; never auto-transmit raw medical records without an approved
recipient role/purpose/audit log; export formats "PDF summary, CSV export,
or MFR-style summary."

This model never stores or references raw `MedicalRecord` file bytes or
`storage_path` - only `content_category` + `export_type` (what kind of
summary, not the underlying document). IDMT is a summary recipient, never a
raw-record viewer (`app/services/medical_record_service.py`'s
`CLINICAL_VIEW_ROLES` deliberately excludes IDMT) - this model's shape
enforces that at the schema level, not just an access check.

Approval is gated through the existing `PendingConfirmation`/
`AdminConfirmationService` two-person-rule queue (a 4th `action_type`,
`"idmt_handoff"`) - the same real mechanism restricted `ReportExport`s
already use, not a parallel approval system.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

EXPORT_TYPES = ("injury_summary", "reconditioning_summary", "medical_record_summary")
EXPORT_FORMATS = ("pdf", "csv", "mfr_summary")
HANDOFF_STATUSES = ("pending_approval", "approved", "rejected", "transmitted", "acknowledged")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class IdmtHandoff(Document):
    """A single documentation handoff prepared for IDMT."""

    user_id: PydanticObjectId
    export_type: str
    content_category: str
    export_format: str
    prepared_by: PydanticObjectId
    recipient_role: str
    status: str = "pending_approval"
    prepared_date: datetime = Field(default_factory=utc_now)
    transmitted_date: datetime | None = None
    acknowledgement_status: str = "not_acknowledged"
    acknowledged_by: PydanticObjectId | None = None
    acknowledged_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "idmt_handoffs"
        indexes = [
            IndexModel([("recipient_role", 1), ("status", 1), ("prepared_date", -1)]),
        ]
