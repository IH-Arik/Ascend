"""Specialist note service (DOCX Section 17 - see model docstring)."""

from __future__ import annotations

from typing import Any

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.core.roles import ADMIN_ROLES, SPECIALIST_ROLES
from app.models.specialist_note import SpecialistNote
from app.models.user import User
from app.schemas.specialist_note import SpecialistNoteCreate
from app.services.audit_log_service import AuditLogService


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
        return await self._serialize(record)

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
        return {"notes": [await self._serialize(n) for n in notes]}

    async def update_status(self, actor: User, note_id: str, new_status: str) -> dict[str, Any]:
        """Only the authoring specialist or Admin may update a note's status."""
        record = await SpecialistNote.get(note_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found.")
        if actor.role not in ADMIN_ROLES and record.specialist_id != actor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the authoring specialist or an Admin may update this note.",
            )

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
        return await self._serialize(record)

    async def _serialize(self, record: SpecialistNote) -> dict[str, Any]:
        specialist = await User.get(record.specialist_id)
        return {
            "id": str(record.id),
            "user_id": str(record.user_id),
            "specialist_id": str(record.specialist_id),
            "specialist_name": specialist.full_name if specialist else None,
            "specialist_type": record.specialist_type,
            "note_date": record.note_date.isoformat(),
            "user_concern": record.user_concern,
            "action_assigned": record.action_assigned,
            "follow_up_needed": record.follow_up_needed,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
        }
