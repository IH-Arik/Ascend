"""Utilization Event tracking service - feeds the quarterly Utilization Report."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.models.user import User
from app.models.utilization_event import UtilizationEvent
from app.schemas.utilization_event import UtilizationEventCreate


class UtilizationService:
    """Log and list training/education/feedback utilization events."""

    async def create(self, staff_lead: User, payload: UtilizationEventCreate) -> dict[str, Any]:
        """Log a new utilization event."""
        record = UtilizationEvent(
            event_type=payload.event_type,
            opportunity_offered=payload.opportunity_offered,
            actual_use=payload.actual_use,
            event_date=payload.event_date,
            staff_lead_id=staff_lead.id,
            attendance_count=payload.attendance_count,
            notes=payload.notes,
        )
        await record.insert()
        return await self._serialize(record)

    async def list_recent(self, days: int = 90) -> dict[str, Any]:
        """Return utilization events from the last N days, newest first."""
        cutoff = date.today() - timedelta(days=days)
        records = await UtilizationEvent.find(UtilizationEvent.event_date >= cutoff).to_list()
        records.sort(key=lambda item: item.event_date, reverse=True)
        return {"events": [await self._serialize(r) for r in records]}

    async def _serialize(self, record: UtilizationEvent) -> dict[str, Any]:
        """Convert a stored event to a transport-safe dict."""
        staff_lead = await User.get(record.staff_lead_id)
        return {
            "id": str(record.id),
            "event_type": record.event_type,
            "opportunity_offered": record.opportunity_offered,
            "actual_use": record.actual_use,
            "event_date": record.event_date.isoformat(),
            "staff_lead_name": staff_lead.full_name if staff_lead else None,
            "attendance_count": record.attendance_count,
            "notes": record.notes,
        }
