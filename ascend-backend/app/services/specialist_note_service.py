"""Specialist note service (DOCX Section 17 - see model docstring)."""

from __future__ import annotations

from typing import Any

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.core.roles import ADMIN_ROLES, SPECIALIST_ROLES
from app.core.security import utc_now
from app.models.specialist_note import DRAFT_EXPIRY_HOURS, SpecialistNote
from app.models.user import User
from app.schemas.specialist_note import SpecialistNoteCreate
from app.services.audit_log_service import AuditLogService

REDACTED_PLACEHOLDER = "[redacted - reveal with reason]"
NOTE_REDACTABLE_FIELDS = ("user_concern", "action_assigned")


class SpecialistNoteService:
    """Create, list, and update the status of real specialist notes."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()

    async def create(
        self, specialist: User, target_user_id: str, payload: SpecialistNoteCreate
    ) -> dict[str, Any]:
        """A specialist records a real note about an operator. Audit logged."""
        target = await User.get(target_user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        if specialist.role not in SPECIALIST_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only a specialist role (Mental Performance/Chaplain/Nutritionist) can author a note.",
            )

        record = SpecialistNote(
            user_id=target.id,
            specialist_id=specialist.id,
            specialist_type=specialist.role,
            user_concern=payload.user_concern,
            action_assigned=payload.action_assigned,
            follow_up_needed=payload.follow_up_needed,
            note_type=payload.note_type,
            escalated=payload.escalated,
        )
        await record.insert()
        await self.audit_log_service.record(
            event_type="specialist_note_created",
            actor_id=specialist.id,
            actor_role=specialist.role,
            target_entity_type="specialist_note",
            target_entity_id=str(record.id),
            summary_message=f"{specialist.role} specialist note recorded for {target.email}.",
        )
        return await self._serialize(record, viewer=specialist)

    async def list_for_user(self, viewer: User, target_user_id: str) -> dict[str, Any]:
        """Real notes for an operator - pathway-siloed unless the viewer is Admin.

        `target_user_id` may be a route-supplied string - coerced to a real
        `PydanticObjectId` before querying (same fix already applied twice
        elsewhere this session - Beanie's `==` doesn't coerce a string to
        match a `PydanticObjectId` field).
        """
        if not isinstance(target_user_id, PydanticObjectId):
            target_user_id = PydanticObjectId(target_user_id)
        notes = await SpecialistNote.find(SpecialistNote.user_id == target_user_id).to_list()
        if viewer.role not in ADMIN_ROLES:
            notes = [n for n in notes if n.specialist_type == viewer.role]
        notes.sort(key=lambda n: n.created_at, reverse=True)
        return {"notes": [await self._serialize(n, viewer=viewer) for n in notes]}

    async def update_status(self, actor: User, note_id: str, new_status: str) -> dict[str, Any]:
        """Only the authoring specialist or Admin may update a note's status."""
        record = await self._get_or_404(note_id)
        self._require_author_or_admin(actor, record)

        record.status = new_status
        await record.save()
        await self.audit_log_service.record(
            event_type="specialist_note_status_changed",
            actor_id=actor.id,
            actor_role=actor.role,
            target_entity_type="specialist_note",
            target_entity_id=str(record.id),
            summary_message=f"Specialist note status changed to {new_status}.",
        )
        return await self._serialize(record, viewer=actor)

    async def sign(self, actor: User, note_id: str) -> dict[str, Any]:
        """The authoring specialist (or Admin) signs a draft note.

        Real 2-state documentation lifecycle (draft -> signed), deliberately
        kept minimal per DOCX 17's "keep simple" language - no revision
        history, no co-signature, no formal chart. A note may still be
        signed after its draft window has passed (`draft_expired` is a
        real, informational flag, not an enforced lock).
        """
        record = await self._get_or_404(note_id)
        self._require_author_or_admin(actor, record)
        if record.documentation_status == "signed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This note is already signed.")

        record.documentation_status = "signed"
        record.signed_at = utc_now()
        await record.save()
        await self.audit_log_service.record(
            event_type="specialist_note_signed",
            actor_id=actor.id,
            actor_role=actor.role,
            target_entity_type="specialist_note",
            target_entity_id=str(record.id),
            summary_message="Specialist note signed.",
        )
        return await self._serialize(record, viewer=actor)

    async def reveal_field(
        self, viewer: User, note_id: str, field_name: str, reason: str, reason_category: str
    ) -> dict[str, Any]:
        """A non-authoring viewer's reason-required, one-time reveal of a redacted field.

        Same real pattern as `MedicalRecordService.reveal_field` - not a
        persisted unmask, every call is audit-logged.
        """
        record = await self._get_or_404(note_id)
        if viewer.role not in ADMIN_ROLES and record.specialist_type != viewer.role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This note is not visible to your role.",
            )
        if field_name not in NOTE_REDACTABLE_FIELDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That field cannot be revealed.")

        await self.audit_log_service.record(
            event_type="specialist_note_field_unredacted",
            actor_id=viewer.id,
            actor_role=viewer.role,
            target_entity_type="specialist_note",
            target_entity_id=str(record.id),
            summary_message=f"[{reason_category}] {field_name}: {reason}",
        )
        return {"field_name": field_name, "value": getattr(record, field_name), "reason_category": reason_category}

    def _require_author_or_admin(self, actor: User, record: SpecialistNote) -> None:
        if actor.role not in ADMIN_ROLES and record.specialist_id != actor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the authoring specialist or an Admin may update this note.",
            )

    async def _get_or_404(self, note_id: str) -> SpecialistNote:
        record = await SpecialistNote.get(note_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found.")
        return record

    async def _serialize(self, record: SpecialistNote, *, viewer: User) -> dict[str, Any]:
        specialist = await User.get(record.specialist_id)
        # Redacted for anyone who isn't the authoring specialist - including
        # Admin, matching the mock's own "redacted by default... require
        # explicit access with reason" language, which doesn't exempt
        # oversight roles.
        is_redacted = viewer.id != record.specialist_id
        draft_expired = (
            record.documentation_status == "draft"
            and (utc_now() - record.created_at).total_seconds() > DRAFT_EXPIRY_HOURS * 3600
        )
        return {
            "id": str(record.id),
            "user_id": str(record.user_id),
            "specialist_id": str(record.specialist_id),
            "specialist_name": specialist.full_name if specialist else None,
            "specialist_type": record.specialist_type,
            "note_date": record.note_date.isoformat(),
            "note_type": record.note_type,
            "escalated": record.escalated,
            "user_concern": REDACTED_PLACEHOLDER if is_redacted else record.user_concern,
            "action_assigned": REDACTED_PLACEHOLDER if is_redacted and record.action_assigned else record.action_assigned,
            "follow_up_needed": record.follow_up_needed,
            "status": record.status,
            "documentation_status": record.documentation_status,
            "signed_at": record.signed_at.isoformat() if record.signed_at else None,
            "draft_expired": draft_expired,
            "is_redacted": is_redacted,
            "created_at": record.created_at.isoformat(),
        }
