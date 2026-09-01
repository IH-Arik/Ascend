"""Reflection entry service (see `app/models/reflection.py`)."""

from __future__ import annotations

from typing import Any

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.core.roles import ADMIN_ROLES
from app.models.reflection import Reflection
from app.models.team_assignment import STATUS_ENABLED, TeamAssignment
from app.models.user import User
from app.schemas.reflection import ReflectionCreate
from app.services.audit_log_service import AuditLogService

CHAPLAIN_PATHWAY_KEY = "Chaplain"


class ReflectionService:
    """Create and list real, private operator-authored reflection entries."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()

    async def create(self, user: User, payload: ReflectionCreate) -> dict[str, Any]:
        """The operator writes a real reflection - requires an active Chaplain opt-in."""
        if not await self._is_opted_in(user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must opt into the Chaplain / Purpose pathway before writing a reflection.",
            )
        record = Reflection(user_id=user.id, theme=payload.theme, body=payload.body)
        await record.insert()
        return self._serialize(record)

    async def list_own(self, user: User) -> dict[str, Any]:
        """The operator's own reflections, most recent first."""
        records = await Reflection.find(Reflection.user_id == user.id).to_list()
        records.sort(key=lambda item: item.created_at, reverse=True)
        return {"reflections": [self._serialize(r) for r in records]}

    async def list_for_user(self, viewer: User, target_user_id: str) -> dict[str, Any]:
        """A Chaplain (or Admin) reads a real user's reflections - gated by live opt-in.

        DOCX-adjacent design: "Revoked consent immediately removes this
        record from view" (Chaplain dashboard mock's own footer text) -
        enforced for real here, not cosmetically. A user who has since
        opted out is correctly refused, even though their past entries
        still exist in storage (they are never deleted on opt-out, only
        hidden from every viewer but the author).
        """
        if not isinstance(target_user_id, PydanticObjectId):
            target_user_id = PydanticObjectId(target_user_id)
        if viewer.role not in ADMIN_ROLES and not await self._is_opted_in(target_user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This user is not currently opted into the Chaplain / Purpose pathway.",
            )
        records = await Reflection.find(Reflection.user_id == target_user_id).to_list()
        records.sort(key=lambda item: item.created_at, reverse=True)

        await self.audit_log_service.record(
            event_type="reflections_viewed",
            actor_id=viewer.id,
            actor_role=viewer.role,
            target_entity_type="reflection_log",
            target_entity_id=str(target_user_id),
            summary_message=f"{viewer.role} viewed reflection entries.",
        )
        return {"reflections": [self._serialize(r) for r in records]}

    async def _is_opted_in(self, user_id: PydanticObjectId) -> bool:
        assignment = await TeamAssignment.find_one(
            TeamAssignment.user_id == user_id, TeamAssignment.pathway_key == CHAPLAIN_PATHWAY_KEY
        )
        return assignment is not None and assignment.status == STATUS_ENABLED

    def _serialize(self, record: Reflection) -> dict[str, Any]:
        return {
            "id": str(record.id),
            "theme": record.theme,
            "body": record.body,
            "length_chars": len(record.body),
            "created_at": record.created_at.isoformat(),
        }
