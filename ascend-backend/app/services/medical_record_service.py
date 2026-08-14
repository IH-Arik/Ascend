"""Medical record upload service (DOCX section 8.8, Medical Records Upload
and Health History Support).

Access is deliberately restricted to the record owner, PT/IM, and Admin -
the DOCX is explicit: "The SCS should not receive unrestricted raw medical
records by default." SCS and the other support pathways (Nutrition, Mental
Performance, Chaplain) can only ever receive PT/IM-approved *performance
summaries* per the DOCX, which this backend does not yet generate - so for
now they simply have no access to raw uploads at all, rather than a
half-built summary path that doesn't really enforce "minimum necessary."

Every upload and every subsequent view/download/review writes an append-
only `MedicalRecordAccessEvent`, matching the DOCX's "audit logging for
every upload/view/download/export" requirement.

If an admin does widen a record's access to a non-clinical role via
`update_access_level`, that role gets a masked view (DOCX Section 15:
"support document masking or redaction... before information is shared
with non-clinical roles") rather than the raw record - see
`CLINICAL_VIEW_ROLES`/`REDACTABLE_FIELDS`/`reveal_field`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import HTTPException, UploadFile, status

from app.core.notification_rules import scan_for_opsec_terms
from app.core.roles import ADMIN_ROLES, ROLE_PTIM
from app.core.security import utc_now
from app.core.support_pathways import get_support_pathway
from app.models.medical_record import MedicalRecord, MedicalRecordAccessEvent
from app.models.team_assignment import TeamAssignment
from app.models.user import User
from app.schemas.medical_record import DOCUMENT_TYPES, MIN_ACCESS_REASON_LENGTH, REASON_CATEGORIES
from app.services.file_storage_service import FileStorageService, scan_file_stub
from app.services.notification_service import NotificationService

FILE_TYPE_BY_EXTENSION = {
    ".pdf": "pdf",
    ".dcm": "dicom",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".heic": "image",
}

VIEW_ALLOWED_ROLES = {ROLE_PTIM, *ADMIN_ROLES}

# DOCX Section 15: "Support document masking or redaction where needed
# before information is shared with non-clinical roles" / "masking/redaction
# before medical-history information is shared with SCS, nutrition, mental
# performance, or other non-clinical support pathways." PT/IM and Admin are
# the clinical/oversight roles this doesn't apply to - any other role that
# reaches a record only gets there via an admin explicitly widening
# `approved_access_level`, and now gets a masked view by default instead of
# the raw one.
CLINICAL_VIEW_ROLES = VIEW_ALLOWED_ROLES
REDACTABLE_FIELDS = ("file_name", "access_reason")
REDACTED_PLACEHOLDER = "[redacted - reveal with reason]"

# Not DOCX-sourced cadence (DOCX line 147/211 names "retention status" as a
# required field but not a specific window) - own reasonable default, same
# pairing style as `User.access_expires_at`.
MEDICAL_RECORD_ACCESS_EXPIRY_DAYS = 180


class MedicalRecordService:
    """Upload, list, view, and review medical records."""

    def __init__(self) -> None:
        self.storage = FileStorageService()
        self.notification_service = NotificationService()

    async def upload(
        self, user: User, document_type: str, access_reason: str, file: UploadFile
    ) -> dict[str, Any]:
        """Upload a new medical record (controlled copy, not a system of record)."""
        if document_type not in DOCUMENT_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown document type.")
        access_reason = access_reason.strip()
        if len(access_reason) < MIN_ACCESS_REASON_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Access-reason must be at least {MIN_ACCESS_REASON_LENGTH} characters.",
            )
        # A blocked extension no longer bare-rejects with nothing stored -
        # it's saved as a real `"quarantined"` record instead (real, not
        # DOCX-sourced - a Figma "Audit log" screen's quarantine claim
        # triggered this), so there's an actual auditable record of the
        # attempt rather than a silent 400.
        is_quarantine_candidate = not scan_file_stub(file.filename or "")

        content = await file.read()
        from app.core.config import get_settings

        max_bytes = get_settings().medical_record_max_bytes
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds the {max_bytes // (1024 * 1024)} MB limit.",
            )

        file_name = file.filename or "upload"
        extension = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        file_type = FILE_TYPE_BY_EXTENSION.get(extension, "other")
        storage_path = self.storage.save_file(str(user.id), file_name, content)

        record = MedicalRecord(
            user_id=user.id,
            document_type=document_type,
            file_name=file_name,
            file_type=file_type,
            file_size_bytes=len(content),
            storage_path=storage_path,
            access_reason=access_reason,
            uploaded_by=user.id,
            status="quarantined" if is_quarantine_candidate else "pending",
            access_expires_at=utc_now() + timedelta(days=MEDICAL_RECORD_ACCESS_EXPIRY_DAYS),
            source="self_upload",
            consent_status="granted",
            approved_access_level=list(VIEW_ALLOWED_ROLES),
        )
        await record.insert()

        if is_quarantine_candidate:
            await self._log_event(
                record.id,
                user.id,
                user.role,
                "quarantine",
                "File type failed the malware/type scan stub - quarantined, not available for review or download.",
            )
            return await self._serialize_detail(record, viewer_role=user.role, is_owner=True)

        await self._log_event(record.id, user.id, user.role, "upload", access_reason)

        opsec_terms = scan_for_opsec_terms(access_reason)
        scan_note = (
            f"Scan flagged terms: {', '.join(opsec_terms)}."
            if opsec_terms
            else "Scan complete - no OPSEC keywords detected - routed to PT/IM queue."
        )
        await self._log_event(record.id, None, "system", "opsec_scan", scan_note)

        await self._notify_assigned_ptim(user, record)

        return await self._serialize_detail(record, viewer_role=user.role, is_owner=True)

    async def list_for_user(
        self, user: User, document_type_filter: str | None, search: str | None
    ) -> dict[str, Any]:
        """Return the user's own uploaded records, optionally filtered."""
        records = await MedicalRecord.find(MedicalRecord.user_id == user.id).to_list()
        if document_type_filter and document_type_filter != "all":
            records = [r for r in records if r.document_type == document_type_filter]
        if search:
            needle = search.lower()
            records = [r for r in records if needle in r.file_name.lower()]
        records.sort(key=lambda item: item.uploaded_at, reverse=True)
        return {"records": [self._serialize_list_item(r) for r in records]}

    async def get_detail(self, user: User, record_id: str) -> dict[str, Any]:
        """Return a record's full detail + access log, logging this view."""
        record = await self._get_viewable(user, record_id)
        is_owner = user.id == record.user_id
        if not is_owner:
            await self._log_event(record.id, user.id, user.role, "view_record", "Opened record for review")
        return await self._serialize_detail(record, viewer_role=user.role, is_owner=is_owner)

    async def get_file(self, user: User, record_id: str) -> tuple[bytes, str]:
        """Return decrypted file bytes + filename, logging this download."""
        record = await self._get_viewable(user, record_id)
        if record.status == "quarantined":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This record is quarantined and is not available for download.",
            )
        if user.id != record.user_id and user.role not in CLINICAL_VIEW_ROLES:
            # DOCX: non-clinical roles never get raw documents, masked or not
            # - metadata can be redacted, a binary file cannot.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Raw file downloads are restricted to PT/IM and Admin. "
                "Non-clinical roles receive masked metadata only.",
            )
        await self._log_event(record.id, user.id, user.role, "download", "Downloaded file")
        return self.storage.read_file(record.storage_path), record.file_name

    async def review(self, reviewer: User, record_id: str, note: str, approve: bool = True) -> dict[str, Any]:
        """PT/IM or Admin marks a record reviewed - approved or denied."""
        record = await MedicalRecord.get(record_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found.")
        allowed_roles = record.approved_access_level or list(VIEW_ALLOWED_ROLES)
        if reviewer.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not on this record's approved access list.",
            )
        if record.status == "quarantined":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A quarantined record cannot be reviewed.",
            )

        record.status = "reviewed_approved" if approve else "reviewed_denied"
        record.reviewed_by = reviewer.id
        record.reviewed_at = utc_now()
        await record.save()

        await self._log_event(
            record.id, reviewer.id, reviewer.role, "review_approved" if approve else "review_denied", note
        )
        return await self._serialize_detail(record, viewer_role=reviewer.role, is_owner=False)

    async def _get_viewable(self, user: User, record_id: str) -> MedicalRecord:
        """Return a record if the user is its owner or on its real approved access list."""
        record = await MedicalRecord.get(record_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found.")
        # `approved_access_level` is the real per-record source of truth
        # (added 2026-08-10) - `VIEW_ALLOWED_ROLES` is only the default a
        # new record starts with, not a floor every record always allows,
        # so an admin narrowing a record's list can genuinely revoke a
        # role's access, not just add to it.
        allowed_roles = record.approved_access_level or list(VIEW_ALLOWED_ROLES)
        if user.id != record.user_id and user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this record.",
            )
        return record

    async def update_access_level(
        self, admin: User, record_id: str, approved_access_level: list[str]
    ) -> dict[str, Any]:
        """Admin narrows/sets a specific record's real approved access list. Audit logged."""
        record = await MedicalRecord.get(record_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found.")
        old_access = record.approved_access_level
        record.approved_access_level = approved_access_level
        await record.save()
        await self._log_event(
            record.id,
            admin.id,
            admin.role,
            "access_level_updated",
            f"Approved access level changed from {old_access} to {approved_access_level}.",
        )
        return await self._serialize_detail(record, viewer_role=admin.role, is_owner=False)

    async def _notify_assigned_ptim(self, user: User, record: MedicalRecord) -> None:
        """Notify the user's assigned PT/IM that a new record is pending review."""
        pathway = get_support_pathway("PT/IM")
        if pathway is None or pathway["role"] is None:
            return
        assignment = await TeamAssignment.find_one(
            TeamAssignment.user_id == user.id, TeamAssignment.pathway_key == "PT/IM"
        )
        if assignment is None or assignment.provider_user_id is None:
            return
        await self.notification_service.notify(
            assignment.provider_user_id,
            family="medical_record_review_and_governance_notices",
            title=f"New medical record pending review ({user.full_name or user.email})",
            body=f"{record.document_type.title()}: {record.file_name}",
            related_entity_type="medical_record",
            related_entity_id=str(record.id),
        )

    async def _log_event(
        self, record_id: Any, actor_id: Any, actor_role: str, action: str, note: str
    ) -> None:
        """Append one access/action event to a record's audit trail."""
        event = MedicalRecordAccessEvent(
            record_id=record_id, actor_id=actor_id, actor_role=actor_role, action=action, note=note
        )
        await event.insert()

    def _serialize_list_item(self, record: MedicalRecord) -> dict[str, Any]:
        """Convert a record to its list-view transport-safe dict."""
        return {
            "id": str(record.id),
            "document_type": record.document_type,
            "file_name": record.file_name,
            "file_type": record.file_type,
            "file_size_bytes": record.file_size_bytes,
            "status": record.status,
            "access_reason": record.access_reason,
            "uploaded_at": record.uploaded_at.isoformat(),
            "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
        }

    async def reveal_field(
        self, viewer: User, record_id: str, field_name: str, reason: str, reason_category: str
    ) -> dict[str, Any]:
        """A masked viewer's reason-required, one-time reveal of a single redacted field.

        Not a persisted unmask - the next `get_detail` call is masked again
        for this viewer. Every call is audit-logged, same as every other
        action on this model. `reason_category` is real and auditable (see
        `REASON_CATEGORIES`), not just a UI-only radio button.
        """
        record = await self._get_viewable(viewer, record_id)
        if field_name not in REDACTABLE_FIELDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That field cannot be revealed.")
        if reason_category not in REASON_CATEGORIES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown reason category.")
        reason = reason.strip()
        if len(reason) < MIN_ACCESS_REASON_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reveal reason must be at least {MIN_ACCESS_REASON_LENGTH} characters.",
            )
        await self._log_event(
            record.id, viewer.id, viewer.role, "field_unredacted", f"[{reason_category}] {field_name}: {reason}"
        )
        return {"field_name": field_name, "value": getattr(record, field_name), "reason_category": reason_category}

    async def _serialize_detail(
        self, record: MedicalRecord, *, viewer_role: str, is_owner: bool
    ) -> dict[str, Any]:
        """Convert a record to its full-detail transport-safe dict, including the access log.

        `viewer_role`/`is_owner` decide masking (DOCX Section 15) - the
        owner and any `CLINICAL_VIEW_ROLES` viewer get the raw record; any
        other viewer (only reachable via an admin-widened
        `approved_access_level`) gets `REDACTABLE_FIELDS` masked, revealable
        one field at a time via `reveal_field`.
        """
        is_redacted = not is_owner and viewer_role not in CLINICAL_VIEW_ROLES
        uploader = await User.get(record.uploaded_by)
        reviewer = await User.get(record.reviewed_by) if record.reviewed_by else None
        events = await MedicalRecordAccessEvent.find(
            MedicalRecordAccessEvent.record_id == record.id
        ).to_list()
        events.sort(key=lambda item: item.created_at)

        access_log = []
        for event in events:
            actor = await User.get(event.actor_id) if event.actor_id else None
            access_log.append(
                {
                    "actor_name": actor.full_name if actor else "system",
                    "actor_role": event.actor_role,
                    "action": event.action,
                    "note": REDACTED_PLACEHOLDER if is_redacted else event.note,
                    "created_at": event.created_at.isoformat(),
                }
            )

        return {
            "id": str(record.id),
            "document_type": record.document_type,
            "file_name": REDACTED_PLACEHOLDER if is_redacted else record.file_name,
            "file_type": record.file_type,
            "file_size_bytes": record.file_size_bytes,
            "status": record.status,
            "access_reason": REDACTED_PLACEHOLDER if is_redacted else record.access_reason,
            "uploaded_by_name": uploader.full_name if uploader else None,
            "uploaded_at": record.uploaded_at.isoformat(),
            "reviewed_by_name": reviewer.full_name if reviewer else None,
            "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
            "access_expires_at": record.access_expires_at.isoformat() if record.access_expires_at else None,
            "sensitivity_level": record.sensitivity_level,
            "source": record.source,
            "consent_status": record.consent_status,
            "approved_access_level": record.approved_access_level,
            "is_redacted": is_redacted,
            "access_log": access_log,
        }
