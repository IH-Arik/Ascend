"""Duty/training restriction service (net-new, not DOCX-sourced - see model docstring).

Release requires two real, checked conditions - see `release_restriction`.
"""

from __future__ import annotations

from typing import Any

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.core.security import utc_now
from app.models.reconditioning_event import ReconditioningEvent
from app.models.reconditioning_plan import ReconditioningPlan
from app.models.restriction import Restriction
from app.models.user import User
from app.schemas.reconditioning import PHASE_LABELS, PHASE_ORDER


class RestrictionService:
    """Add, list, and release real duty/training restrictions."""

    async def add_restriction(
        self, target_user: User, description: str, required_phase: str, created_by: Any
    ) -> dict[str, Any]:
        """Record a real restriction and append a real timeline event."""
        record = Restriction(
            user_id=target_user.id,
            description=description,
            required_phase=required_phase,
            created_by=created_by,
        )
        await record.insert()
        await self._log_event(
            target_user.id,
            "restriction_added",
            f"{description} (requires {PHASE_LABELS.get(required_phase, required_phase)})",
            created_by,
        )
        return await self._serialize(record)

    async def release_restriction(self, restriction_id: str, actor: Any) -> dict[str, Any]:
        """Explicit signoff release - only succeeds once the plan has genuinely reached the required phase.

        Two real conditions, both checked: (1) the operator's current
        `ReconditioningPlan.phase` has actually reached `required_phase`,
        (2) this explicit signoff call. Reaching the phase alone never
        auto-releases a restriction.
        """
        record = await Restriction.get(restriction_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restriction not found.")
        if record.status == "released":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Restriction already released.")

        plan = await ReconditioningPlan.find_one(ReconditioningPlan.user_id == record.user_id)
        current_phase = plan.phase if plan else None
        if current_phase is None or PHASE_ORDER.get(current_phase, -1) < PHASE_ORDER[record.required_phase]:
            current_label = PHASE_LABELS.get(current_phase, current_phase or "no plan on file")
            required_label = PHASE_LABELS.get(record.required_phase, record.required_phase)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot release: current phase ({current_label}) has not yet reached the required phase ({required_label}).",
            )

        record.status = "released"
        record.released_by = actor
        record.released_at = utc_now()
        await record.save()
        await self._log_event(record.user_id, "restriction_released", record.description, actor)
        return await self._serialize(record)

    async def list_for_user(self, user_id: Any) -> dict[str, Any]:
        """Real active + released restrictions, each with a live phase-requirement check."""
        if not isinstance(user_id, PydanticObjectId):
            user_id = PydanticObjectId(user_id)
        records = await Restriction.find(Restriction.user_id == user_id).to_list()
        records.sort(key=lambda r: r.created_at)
        plan = await ReconditioningPlan.find_one(ReconditioningPlan.user_id == user_id)
        current_phase = plan.phase if plan else None
        return {"restrictions": [await self._serialize(r, current_phase) for r in records]}

    async def _log_event(self, user_id: Any, event_type: str, detail: str, recorded_by: Any) -> None:
        await ReconditioningEvent(
            user_id=user_id, event_type=event_type, detail=detail, recorded_by=recorded_by
        ).insert()

    async def _serialize(self, record: Restriction, current_phase: str | None = "__unset__") -> dict[str, Any]:
        if current_phase == "__unset__":
            plan = await ReconditioningPlan.find_one(ReconditioningPlan.user_id == record.user_id)
            current_phase = plan.phase if plan else None
        phase_requirement_met = (
            current_phase is not None and PHASE_ORDER.get(current_phase, -1) >= PHASE_ORDER[record.required_phase]
        )
        return {
            "id": str(record.id),
            "description": record.description,
            "required_phase": record.required_phase,
            "required_phase_label": PHASE_LABELS.get(record.required_phase, record.required_phase),
            "status": record.status,
            "phase_requirement_met": phase_requirement_met,
            "created_at": record.created_at.isoformat(),
            "released_at": record.released_at.isoformat() if record.released_at else None,
        }
