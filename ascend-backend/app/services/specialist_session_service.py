"""Specialist session scheduling service (see `app/models/specialist_session.py`)."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException, status

from app.core.roles import SPECIALIST_ROLES
from app.core.security import utc_now
from app.models.specialist_session import ChecklistItem, SpecialistSession
from app.models.user import User
from app.schemas.specialist_session import ChecklistItemToggle, SpecialistSessionCreate, SpecialistSessionUpdate
from app.services.audit_log_service import AuditLogService

DURATION_WINDOW_DAYS = 30


class SpecialistSessionService:
    """Create and list real scheduled specialist sessions (MP/Nutritionist/Chaplain)."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()

    async def create(self, provider: User, payload: SpecialistSessionCreate) -> dict[str, Any]:
        """Schedule a real individual or group specialist session."""
        if provider.role not in SPECIALIST_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only a specialist role (Mental Performance/Nutritionist/Chaplain) can lead this session.",
            )
        attendee_ids = []
        for user_id in payload.attendee_user_ids:
            attendee = await User.get(user_id)
            if attendee is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {user_id} not found.")
            attendee_ids.append(attendee.id)

        record = SpecialistSession(
            provider_id=provider.id,
            provider_role=provider.role,
            session_date=payload.session_date,
            start_time=payload.start_time,
            session_type=payload.session_type,
            attendee_user_ids=attendee_ids,
            group_label=payload.group_label,
            topic=payload.topic,
            capacity=payload.capacity,
            planned_duration_minutes=payload.planned_duration_minutes,
            prep_checklist=[ChecklistItem(label=label) for label in payload.prep_checklist_items],
            created_by=provider.id,
        )
        await record.insert()

        await self.audit_log_service.record(
            event_type="specialist_session_scheduled",
            actor_id=provider.id,
            actor_role=provider.role,
            target_entity_type="specialist_session",
            target_entity_id=str(record.id),
            summary_message=f"Scheduled a {record.session_type} {provider.role} session on {record.session_date.isoformat()}.",
        )
        return await self._serialize(record)

    async def update(self, session_id: str, provider: User, payload: SpecialistSessionUpdate) -> dict[str, Any]:
        """Update a session's status.

        Real duration tracking: moving to "completed" stamps `ended_at` only
        if the session was actually started (`started_at` set via `start()`)
        and hasn't already been stopped - a session marked completed without
        ever being started keeps `ended_at` unset, so it's excluded from the
        average-duration metric rather than counted as 0 minutes.
        """
        record = await self._get_or_404(session_id)
        if payload.status is not None:
            record.status = payload.status
            if payload.status == "completed" and record.started_at is not None and record.ended_at is None:
                record.ended_at = utc_now()
        record.updated_at = utc_now()
        await record.save()

        await self.audit_log_service.record(
            event_type="specialist_session_updated",
            actor_id=provider.id,
            actor_role=provider.role,
            target_entity_type="specialist_session",
            target_entity_id=str(record.id),
            summary_message=f"Updated specialist session ({record.session_date.isoformat()}) to status '{record.status}'.",
        )
        return await self._serialize(record)

    async def start(self, session_id: str, provider: User) -> dict[str, Any]:
        """Actually start a real, scheduled session - stamps `started_at` for real duration tracking."""
        record = await self._get_or_404(session_id)
        if record.status != "scheduled":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only a scheduled session can be started.")

        record.status = "in_progress"
        record.started_at = utc_now()
        record.updated_at = utc_now()
        await record.save()

        await self.audit_log_service.record(
            event_type="specialist_session_started",
            actor_id=provider.id,
            actor_role=provider.role,
            target_entity_type="specialist_session",
            target_entity_id=str(record.id),
            summary_message=f"Started specialist session ({record.session_date.isoformat()}).",
        )
        return await self._serialize(record)

    async def toggle_checklist_item(self, session_id: str, provider: User, payload: ChecklistItemToggle) -> dict[str, Any]:
        """Check/uncheck one real prep-checklist item, matched by its exact label."""
        record = await self._get_or_404(session_id)
        item = next((i for i in record.prep_checklist if i.label == payload.label), None)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist item not found on this session.")

        item.done = payload.done
        record.updated_at = utc_now()
        await record.save()
        return await self._serialize(record)

    async def list_today(self, provider: User | None = None) -> dict[str, Any]:
        """Return every real session scheduled for today - the caller's own if given, else all."""
        return await self._list_for_date(date.today(), provider)

    async def list_upcoming(self, provider: User | None = None, days: int = 14) -> dict[str, Any]:
        """Return every real session scheduled in the next N days (today included)."""
        today = date.today()
        end = today + timedelta(days=days)
        query = [
            SpecialistSession.session_date >= today,
            SpecialistSession.session_date <= end,
            SpecialistSession.status != "cancelled",
        ]
        if provider is not None:
            query.append(SpecialistSession.provider_id == provider.id)
        records = await SpecialistSession.find(*query).to_list()
        records.sort(key=lambda item: (item.session_date, item.start_time))
        return {"window_days": days, "sessions": [await self._serialize(r) for r in records]}

    async def get_queue_summary(self, provider: User) -> dict[str, Any]:
        """Real "Today"/"This week"/"Prep ready"/"Avg duration" consult-queue counts.

        Not DOCX-sourced (the Figma mock's consult-queue header showed these
        4 metric cards with no real backend behind "Prep ready" or "Avg
        duration" at the time). Both are now real: `prep_ready_count` counts
        today's sessions whose `prep_checklist` is non-empty and every item
        is done; `avg_duration_minutes` averages `ended_at - started_at`
        across this provider's own completed sessions in the last 30 days
        that were actually started via `start()` - sessions completed
        without ever being started have no duration and are excluded, not
        counted as 0.

        `today_follow_up_count` vs `today_new_count` is derived, not a
        stored field: an attendee counts as a follow-up if this same
        provider has any earlier real session with them (any status),
        otherwise it's their first, counted as new.
        """
        today = date.today()
        week_start = today - timedelta(days=today.weekday())  # Monday
        week_end = week_start + timedelta(days=4)  # Friday
        duration_cutoff = today - timedelta(days=DURATION_WINDOW_DAYS)

        today_sessions, week_sessions, duration_sessions = await asyncio.gather(
            SpecialistSession.find(
                SpecialistSession.provider_id == provider.id,
                SpecialistSession.session_date == today,
                SpecialistSession.status != "cancelled",
            ).to_list(),
            SpecialistSession.find(
                SpecialistSession.provider_id == provider.id,
                SpecialistSession.session_date >= week_start,
                SpecialistSession.session_date <= week_end,
                SpecialistSession.status != "cancelled",
            ).to_list(),
            SpecialistSession.find(
                SpecialistSession.provider_id == provider.id,
                SpecialistSession.session_date >= duration_cutoff,
                SpecialistSession.status == "completed",
            ).to_list(),
        )

        follow_up_count = 0
        new_count = 0
        prep_ready_count = 0
        for session in today_sessions:
            has_prior = await SpecialistSession.find(
                SpecialistSession.provider_id == provider.id,
                SpecialistSession.session_date < today,
                {"attendee_user_ids": {"$in": session.attendee_user_ids}},
            ).count()
            if has_prior > 0:
                follow_up_count += 1
            else:
                new_count += 1
            if session.prep_checklist and all(item.done for item in session.prep_checklist):
                prep_ready_count += 1

        durations_minutes = [
            (s.ended_at - s.started_at).total_seconds() / 60
            for s in duration_sessions
            if s.started_at is not None and s.ended_at is not None
        ]
        avg_duration_minutes = round(sum(durations_minutes) / len(durations_minutes)) if durations_minutes else None

        return {
            "today_count": len(today_sessions),
            "today_follow_up_count": follow_up_count,
            "today_new_count": new_count,
            "today_prep_ready_count": prep_ready_count,
            "week_count": len(week_sessions),
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "avg_duration_minutes": avg_duration_minutes,
            "duration_window_days": DURATION_WINDOW_DAYS,
            "duration_sample_size": len(durations_minutes),
        }

    async def _list_for_date(self, target_date: date, provider: User | None) -> dict[str, Any]:
        query = [SpecialistSession.session_date == target_date, SpecialistSession.status != "cancelled"]
        if provider is not None:
            query.append(SpecialistSession.provider_id == provider.id)
        records = await SpecialistSession.find(*query).to_list()
        records.sort(key=lambda item: item.start_time)
        return {"date": target_date.isoformat(), "sessions": [await self._serialize(r) for r in records]}

    async def _get_or_404(self, session_id: str) -> SpecialistSession:
        record = await SpecialistSession.get(session_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Specialist session not found.")
        return record

    async def _serialize(self, record: SpecialistSession) -> dict[str, Any]:
        provider = await User.get(record.provider_id)
        attendee_count = len(record.attendee_user_ids)
        duration_minutes = (
            round((record.ended_at - record.started_at).total_seconds() / 60)
            if record.started_at is not None and record.ended_at is not None
            else None
        )
        return {
            "id": str(record.id),
            "provider_id": str(record.provider_id),
            "provider_name": provider.full_name if provider else None,
            "provider_role": record.provider_role,
            "session_date": record.session_date.isoformat(),
            "start_time": record.start_time,
            "session_type": record.session_type,
            "attendee_user_ids": [str(uid) for uid in record.attendee_user_ids],
            "attendee_count": attendee_count,
            "group_label": record.group_label,
            "topic": record.topic,
            "capacity": record.capacity,
            "capacity_pct": (
                round(attendee_count / record.capacity * 100, 1) if record.capacity else None
            ),
            "planned_duration_minutes": record.planned_duration_minutes,
            "status": record.status,
            "prep_checklist": [item.model_dump() for item in record.prep_checklist],
            "prep_ready": bool(record.prep_checklist) and all(item.done for item in record.prep_checklist),
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "ended_at": record.ended_at.isoformat() if record.ended_at else None,
            "duration_minutes": duration_minutes,
            "created_at": record.created_at.isoformat(),
        }
