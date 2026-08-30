"""Group training-session scheduling service (see `app/models/pt_session.py`)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.core.roles import ROLE_PTIM, ROLE_SCS
from app.core.security import utc_now
from app.models.pt_session import PTSession
from app.models.user import User
from app.schemas.pt_session import FOCUS_LABELS, PTSessionCreate, PTSessionUpdate
from app.services.audit_log_service import AuditLogService

LEAD_PROVIDER_ROLES = (ROLE_SCS, ROLE_PTIM)


class PTSessionService:
    """Create and list real scheduled group training sessions."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()

    async def create(self, admin: User, payload: PTSessionCreate) -> dict[str, Any]:
        """Schedule a real group training session."""
        lead_provider = admin
        if payload.lead_provider_id:
            resolved = await User.get(payload.lead_provider_id)
            if resolved is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead provider not found.")
            lead_provider = resolved

        if lead_provider.role not in LEAD_PROVIDER_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The lead provider must be SCS or PT/IM (got '{lead_provider.role}').",
            )

        record = PTSession(
            lead_provider_id=lead_provider.id,
            lead_provider_role=lead_provider.role,
            session_date=payload.session_date,
            start_time=payload.start_time,
            group_label=payload.group_label,
            focus=payload.focus,
            capacity=payload.capacity,
            unit_id=payload.unit_id,
            created_by=admin.id,
        )
        await record.insert()

        await self.audit_log_service.record(
            event_type="pt_session_scheduled",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="pt_session",
            target_entity_id=str(record.id),
            summary_message=f"Scheduled a {record.focus} session ('{record.group_label}') on {record.session_date.isoformat()}.",
        )
        return await self._serialize(record)

    async def update(self, session_id: str, admin: User, payload: PTSessionUpdate) -> dict[str, Any]:
        """Update a session's status or capacity."""
        record = await self._get_or_404(session_id)
        if payload.status is not None:
            record.status = payload.status
        if payload.capacity is not None:
            record.capacity = payload.capacity
        record.updated_at = utc_now()
        await record.save()

        await self.audit_log_service.record(
            event_type="pt_session_updated",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="pt_session",
            target_entity_id=str(record.id),
            summary_message=f"Updated session '{record.group_label}' ({record.session_date.isoformat()}).",
        )
        return await self._serialize(record)

    async def add_attendee(self, session_id: str, admin: User, user_id: str) -> dict[str, Any]:
        """Enroll one real attendee in a session. 400s if already full or already enrolled."""
        record = await self._get_or_404(session_id)
        attendee = await User.get(user_id)
        if attendee is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        if attendee.id in record.attendee_user_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This user is already enrolled.")
        if len(record.attendee_user_ids) >= record.capacity:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This session is at capacity.")

        record.attendee_user_ids.append(attendee.id)
        record.updated_at = utc_now()
        await record.save()

        await self.audit_log_service.record(
            event_type="pt_session_attendee_added",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="pt_session",
            target_entity_id=str(record.id),
            summary_message=f"Enrolled {attendee.full_name or attendee.email} in '{record.group_label}' "
            f"({record.session_date.isoformat()}).",
        )
        return await self._serialize(record)

    async def remove_attendee(self, session_id: str, admin: User, user_id: str) -> dict[str, Any]:
        """Remove one real attendee from a session."""
        record = await self._get_or_404(session_id)
        target_id = PydanticObjectId(user_id)
        if target_id not in record.attendee_user_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This user is not enrolled.")

        record.attendee_user_ids.remove(target_id)
        record.updated_at = utc_now()
        await record.save()

        await self.audit_log_service.record(
            event_type="pt_session_attendee_removed",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="pt_session",
            target_entity_id=str(record.id),
            summary_message=f"Removed an attendee from '{record.group_label}' ({record.session_date.isoformat()}).",
        )
        return await self._serialize(record)

    async def list_today(self) -> dict[str, Any]:
        """Return every real session scheduled for today, across all providers."""
        return await self._list_for_date(date.today())

    async def list_upcoming(self, days: int = 14) -> dict[str, Any]:
        """Return every real session scheduled in the next N days (today included)."""
        today = date.today()
        end = today + timedelta(days=days)
        records = await PTSession.find(
            PTSession.session_date >= today,
            PTSession.session_date <= end,
            PTSession.status != "cancelled",
        ).to_list()
        records.sort(key=lambda item: (item.session_date, item.start_time))
        return {"window_days": days, "sessions": [await self._serialize(r) for r in records]}

    async def _list_for_date(self, target_date: date) -> dict[str, Any]:
        records = await PTSession.find(
            PTSession.session_date == target_date,
            PTSession.status != "cancelled",
        ).to_list()
        records.sort(key=lambda item: item.start_time)
        return {"date": target_date.isoformat(), "sessions": [await self._serialize(r) for r in records]}

    async def _get_or_404(self, session_id: str) -> PTSession:
        record = await PTSession.get(session_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PT session not found.")
        return record

    async def _serialize(self, record: PTSession) -> dict[str, Any]:
        lead = await User.get(record.lead_provider_id)
        enrolled_count = len(record.attendee_user_ids)
        return {
            "id": str(record.id),
            "lead_provider_id": str(record.lead_provider_id),
            "lead_provider_name": lead.full_name if lead else None,
            "lead_provider_role": record.lead_provider_role,
            "session_date": record.session_date.isoformat(),
            "start_time": record.start_time,
            "group_label": record.group_label,
            "focus": record.focus,
            "focus_label": FOCUS_LABELS.get(record.focus, record.focus),
            "capacity": record.capacity,
            "enrolled_count": enrolled_count,
            "capacity_pct": round(enrolled_count / record.capacity * 100, 1) if record.capacity else 0.0,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
        }
