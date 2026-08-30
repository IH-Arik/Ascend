"""Provider leave/TDY tracking service (see `app/models/leave_record.py`)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.models.leave_record import LeaveRecord
from app.models.user import User
from app.schemas.leave_record import LEAVE_TYPE_LABELS, LeaveRecordCreate
from app.services.audit_log_service import AuditLogService


class LeaveService:
    """Log and list real provider leave/TDY/training/medical absence."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()

    async def create(self, admin: User, payload: LeaveRecordCreate) -> dict[str, Any]:
        """Log a real block of leave/TDY/training/medical absence."""
        target = admin
        if payload.user_id:
            resolved = await User.get(payload.user_id)
            if resolved is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
            target = resolved

        record = LeaveRecord(
            user_id=target.id,
            leave_type=payload.leave_type,
            start_date=payload.start_date,
            end_date=payload.end_date,
            note=payload.note,
            created_by=admin.id,
        )
        await record.insert()

        await self.audit_log_service.record(
            event_type="leave_logged",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="leave_record",
            target_entity_id=str(record.id),
            summary_message=f"Logged {record.leave_type} for {target.full_name or target.email} "
            f"({record.start_date.isoformat()} - {record.end_date.isoformat()}).",
        )
        return await self._serialize(record)

    async def delete(self, leave_id: str, admin: User) -> None:
        """Remove a real leave record (e.g. entered in error)."""
        record = await self._get_or_404(leave_id)
        await record.delete()
        await self.audit_log_service.record(
            event_type="leave_deleted",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="leave_record",
            target_entity_id=leave_id,
            summary_message=f"Deleted a logged {record.leave_type} record.",
        )

    async def list_for_user(self, user_id: str, days: int = 90) -> dict[str, Any]:
        """Return a user's own leave history for the last N days."""
        cutoff = date.today() - timedelta(days=days)
        oid = user_id if isinstance(user_id, PydanticObjectId) else PydanticObjectId(user_id)
        records = await LeaveRecord.find(
            LeaveRecord.user_id == oid,
            LeaveRecord.end_date >= cutoff,
        ).to_list()
        records.sort(key=lambda item: item.start_date, reverse=True)
        return {"window_days": days, "records": [await self._serialize(r) for r in records]}

    async def list_overlap_window(self, days: int = 30) -> dict[str, Any]:
        """Return every real leave record overlapping the next N days, plus real overlapping pairs.

        Not a fabricated severity label - `overlapping_pairs` is computed
        directly from the real date ranges (two records overlap if their
        [start_date, end_date] windows intersect), nothing guessed.
        """
        today = date.today()
        window_end = today + timedelta(days=days)
        records = await LeaveRecord.find(
            LeaveRecord.start_date <= window_end,
            LeaveRecord.end_date >= today,
        ).to_list()
        records.sort(key=lambda item: item.start_date)

        overlapping_pairs: list[dict[str, Any]] = []
        for i, a in enumerate(records):
            for b in records[i + 1 :]:
                latest_start = max(a.start_date, b.start_date)
                earliest_end = min(a.end_date, b.end_date)
                if latest_start <= earliest_end:
                    overlapping_pairs.append(
                        {
                            "record_id_a": str(a.id),
                            "record_id_b": str(b.id),
                            "overlap_start": latest_start.isoformat(),
                            "overlap_end": earliest_end.isoformat(),
                            "overlap_days": (earliest_end - latest_start).days + 1,
                        }
                    )

        return {
            "window_days": days,
            "records": [await self._serialize(r) for r in records],
            "overlapping_pairs": overlapping_pairs,
        }

    async def _get_or_404(self, leave_id: str) -> LeaveRecord:
        record = await LeaveRecord.get(leave_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave record not found.")
        return record

    async def _serialize(self, record: LeaveRecord) -> dict[str, Any]:
        user = await User.get(record.user_id)
        return {
            "id": str(record.id),
            "user_id": str(record.user_id),
            "user_name": user.full_name if user else None,
            "leave_type": record.leave_type,
            "leave_type_label": LEAVE_TYPE_LABELS.get(record.leave_type, record.leave_type),
            "start_date": record.start_date.isoformat(),
            "end_date": record.end_date.isoformat(),
            "note": record.note,
            "created_at": record.created_at.isoformat(),
        }
