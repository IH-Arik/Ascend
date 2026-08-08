"""Reconditioning plan service.

One active plan per user (upserted). Only surfaced to the operator if a
PT/IM or SCS has actually created one - `available: false` otherwise,
never a fabricated default plan.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core.security import utc_now
from app.models.reconditioning_plan import ReconditioningPlan
from app.models.user import User
from app.schemas.reconditioning import CLEARANCE_LABELS, PHASE_LABELS, ReconditioningPlanUpdate


class ReconditioningService:
    """Read and update a user's reconditioning plan."""

    async def get_for_user(self, user_id: Any) -> dict[str, Any]:
        """Return the current reconditioning plan for a user, if one exists."""
        record = await ReconditioningPlan.find_one(ReconditioningPlan.user_id == user_id)
        if record is None:
            return {"available": False}
        return self._serialize(record)

    async def upsert_for_user(
        self, target_user: User, payload: ReconditioningPlanUpdate, updated_by: Any
    ) -> dict[str, Any]:
        """Create or update the reconditioning plan for a user (PT/IM/SCS/Admin only)."""
        record = await ReconditioningPlan.find_one(ReconditioningPlan.user_id == target_user.id)
        if record is None:
            record = ReconditioningPlan(user_id=target_user.id, phase_started_on=date.today())

        if record.phase != payload.phase:
            record.phase_started_on = date.today()

        record.phase = payload.phase
        record.sessions_completed = payload.sessions_completed
        record.sessions_total = payload.sessions_total
        record.cadence_note = payload.cadence_note
        record.injury_flags = payload.injury_flags
        record.ptim_clearance_status = payload.ptim_clearance_status
        record.next_review_date = payload.next_review_date
        record.updated_by = updated_by
        record.updated_at = utc_now()
        await record.save()
        return self._serialize(record)

    def _serialize(self, record: ReconditioningPlan) -> dict[str, Any]:
        """Convert a stored reconditioning plan to a transport-safe dict."""
        return {
            "available": True,
            "phase": record.phase,
            "phase_label": PHASE_LABELS.get(record.phase, record.phase),
            "days_in_phase": (date.today() - record.phase_started_on).days,
            "sessions_completed": record.sessions_completed,
            "sessions_total": record.sessions_total,
            "cadence_note": record.cadence_note,
            "injury_flags": record.injury_flags,
            "ptim_clearance_status": record.ptim_clearance_status,
            "ptim_clearance_label": CLEARANCE_LABELS.get(
                record.ptim_clearance_status, record.ptim_clearance_status
            ),
            "next_review_date": record.next_review_date.isoformat() if record.next_review_date else None,
            "updated_at": record.updated_at.isoformat(),
        }
