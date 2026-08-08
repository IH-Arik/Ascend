"""Equipment and Supply Gap Tracker service (DOCX section 8.7)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.security import utc_now
from app.models.equipment_gap import EquipmentGap
from app.models.user import User
from app.schemas.equipment_gap import EquipmentGapCreate, EquipmentGapUpdate


class EquipmentGapService:
    """Log, list, and update equipment/supply shortfalls (SCS/PT-IM/Admin)."""

    async def create(self, user: User, payload: EquipmentGapCreate) -> dict[str, Any]:
        """Log a new equipment/supply gap."""
        record = EquipmentGap(
            item=payload.item,
            supply_need=payload.supply_need,
            priority=payload.priority,
            requested_by=user.id,
        )
        await record.insert()
        return await self._serialize(record)

    async def list_all(self, status_filter: str | None = None) -> dict[str, Any]:
        """Return all tracked equipment/supply gaps, optionally filtered by status."""
        records = await EquipmentGap.find().to_list()
        if status_filter:
            records = [r for r in records if r.status == status_filter]
        records.sort(key=lambda item: item.date_identified, reverse=True)
        return {"gaps": [await self._serialize(r) for r in records]}

    async def update_status(self, gap_id: str, payload: EquipmentGapUpdate) -> dict[str, Any]:
        """Update a gap's status and/or report-inclusion flag."""
        record = await EquipmentGap.get(gap_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gap not found.")
        record.status = payload.status
        if payload.included_in_report is not None:
            record.included_in_report = payload.included_in_report
        record.updated_at = utc_now()
        await record.save()
        return await self._serialize(record)

    async def _serialize(self, record: EquipmentGap) -> dict[str, Any]:
        """Convert a stored gap to a transport-safe dict."""
        requester = await User.get(record.requested_by)
        return {
            "id": str(record.id),
            "item": record.item,
            "supply_need": record.supply_need,
            "priority": record.priority,
            "requested_by_name": requester.full_name if requester else None,
            "date_identified": record.date_identified.isoformat(),
            "status": record.status,
            "included_in_report": record.included_in_report,
        }
