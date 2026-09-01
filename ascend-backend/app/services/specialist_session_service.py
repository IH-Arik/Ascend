"""Specialist session scheduling service (see `app/models/specialist_session.py`)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException, status

from app.core.roles import SPECIALIST_ROLES
from app.core.security import utc_now
from app.models.specialist_session import SpecialistSession
from app.models.user import User
from app.schemas.specialist_session import SpecialistSessionCreate, SpecialistSessionUpdate
from app.services.audit_log_service import AuditLogService


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
        """Update a session's status."""
        record = await self._get_or_404(session_id)
        if payload.status is not None:
            record.status = payload.status
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
            "status": record.status,
            "created_at": record.created_at.isoformat(),
        }
