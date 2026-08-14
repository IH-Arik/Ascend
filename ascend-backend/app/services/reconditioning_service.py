"""Reconditioning plan service.

One active plan per user (upserted). Only surfaced to the operator if a
PT/IM or SCS has actually created one - `available: false` otherwise,
never a fabricated default plan.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from beanie import PydanticObjectId

from app.core.security import utc_now
from app.models.reconditioning_event import ReconditioningEvent
from app.models.reconditioning_plan import ReconditioningPlan
from app.models.user import User
from app.schemas.reconditioning import (
    CLEARANCE_LABELS,
    PHASE_LABELS,
    SCS_COORDINATION_LABELS,
    ReconditioningPlanUpdate,
)


class ReconditioningService:
    """Read and update a user's reconditioning plan.

    `upsert_for_user` writes one real `ReconditioningEvent` per field that
    actually changed value - the basis for the real reconditioning-event
    timeline (net-new, not DOCX-sourced - see `app/models/reconditioning_event.py`).
    """

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
        is_new = record is None
        if is_new:
            record = ReconditioningPlan(user_id=target_user.id, phase_started_on=date.today())

        if record.phase != payload.phase:
            record.phase_started_on = date.today()

        old_phase, old_clearance, old_severity = record.phase, record.ptim_clearance_status, record.severity_level

        record.phase = payload.phase
        record.sessions_completed = payload.sessions_completed
        record.sessions_total = payload.sessions_total
        record.cadence_note = payload.cadence_note
        record.injury_flags = payload.injury_flags
        record.ptim_clearance_status = payload.ptim_clearance_status
        record.next_review_date = payload.next_review_date
        record.limitation_flag = payload.limitation_flag
        record.rehab_strategy_summary = payload.rehab_strategy_summary
        record.scs_coordination_status = payload.scs_coordination_status
        record.severity_level = payload.severity_level
        record.injury_reported_on = payload.injury_reported_on
        record.updated_by = updated_by
        record.updated_at = utc_now()
        await record.save()

        if is_new:
            await self._log_event(target_user.id, "plan_created", "Reconditioning plan created.", updated_by)
        else:
            if old_phase != record.phase:
                await self._log_event(
                    target_user.id,
                    "phase_changed",
                    f"{PHASE_LABELS.get(old_phase, old_phase)} -> {PHASE_LABELS.get(record.phase, record.phase)}",
                    updated_by,
                )
            if old_clearance != record.ptim_clearance_status:
                await self._log_event(
                    target_user.id,
                    "clearance_changed",
                    f"{CLEARANCE_LABELS.get(old_clearance, old_clearance)} -> "
                    f"{CLEARANCE_LABELS.get(record.ptim_clearance_status, record.ptim_clearance_status)}",
                    updated_by,
                )
            if old_severity != record.severity_level:
                await self._log_event(
                    target_user.id,
                    "severity_changed",
                    f"{old_severity or 'not set'} -> {record.severity_level or 'not set'}",
                    updated_by,
                )

        return self._serialize(record)

    async def get_timeline(self, user_id: Any) -> dict[str, Any]:
        """Real, append-only reconditioning-event history for a user.

        `user_id` may be a route-supplied string - coerced to a real
        `PydanticObjectId` before querying, same fix already applied to
        `CoverageService` (Beanie's `==` doesn't coerce a string to match a
        `PydanticObjectId` field, so an uncoerced string silently matches
        nothing).
        """
        if not isinstance(user_id, PydanticObjectId):
            user_id = PydanticObjectId(user_id)
        events = await ReconditioningEvent.find(ReconditioningEvent.user_id == user_id).to_list()
        events.sort(key=lambda e: e.created_at)
        return {
            "events": [
                {
                    "event_type": e.event_type,
                    "detail": e.detail,
                    "created_at": e.created_at.isoformat(),
                }
                for e in events
            ]
        }

    async def _log_event(self, user_id: Any, event_type: str, detail: str, recorded_by: Any) -> None:
        """Append one real event to a user's reconditioning-event timeline."""
        await ReconditioningEvent(
            user_id=user_id, event_type=event_type, detail=detail, recorded_by=recorded_by
        ).insert()

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
            "limitation_flag": record.limitation_flag,
            "rehab_strategy_summary": record.rehab_strategy_summary,
            "scs_coordination_status": record.scs_coordination_status,
            "scs_coordination_label": SCS_COORDINATION_LABELS.get(
                record.scs_coordination_status, record.scs_coordination_status
            ),
            "severity_level": record.severity_level,
            "injury_reported_on": record.injury_reported_on.isoformat() if record.injury_reported_on else None,
            # Derived, not stored - same real-derivation pattern as
            # `days_in_phase` above, so it can never go stale independently
            # of `injury_reported_on`/`phase`.
            "days_out": (
                (date.today() - record.injury_reported_on).days
                if record.injury_reported_on and record.phase != "completed"
                else None
            ),
            "updated_at": record.updated_at.isoformat(),
        }
