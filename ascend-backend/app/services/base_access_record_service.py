"""Base access / badge / pass service (DOCX Section 14 Compliance Item)."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException, status

from app.core.security import utc_now
from app.models.base_access_record import BaseAccessRecord
from app.models.user import User
from app.schemas.base_access_record import BaseAccessRecordUpsert
from app.services.audit_log_service import AuditLogService


class BaseAccessRecordService:
    """Record and list real base access / badge / pass items for staff."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()

    async def upsert(self, admin: User, user_id: str, payload: BaseAccessRecordUpsert) -> dict[str, Any]:
        """Admin records or updates one staff member's most recent base access item. Audit logged."""
        target = await User.get(user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        existing_records = (
            await BaseAccessRecord.find(BaseAccessRecord.user_id == target.id)
            .sort(-BaseAccessRecord.created_at)
            .limit(1)
            .to_list()
        )
        record = existing_records[0] if existing_records else None
        is_new = record is None
        if is_new:
            record = BaseAccessRecord(user_id=target.id, request_date=payload.request_date, recorded_by=admin.id)

        record.request_date = payload.request_date
        record.approval_status = payload.approval_status
        record.expiration_date = payload.expiration_date
        record.return_required = payload.return_required
        record.returned_date = payload.returned_date
        record.recorded_by = admin.id
        record.updated_at = utc_now()
        await record.save()

        await self.audit_log_service.record(
            event_type="base_access_recorded" if is_new else "base_access_updated",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="base_access_record",
            target_entity_id=str(record.id),
            summary_message=f"Base access/badge/pass recorded for {target.email} - {payload.approval_status}.",
        )
        return await self._serialize(record, target)

    async def list_for_user(self, user_id: str) -> dict[str, Any]:
        """Real base access items recorded for one staff member, newest first."""
        target = await User.get(user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        records = await BaseAccessRecord.find(BaseAccessRecord.user_id == target.id).to_list()
        records.sort(key=lambda r: r.created_at, reverse=True)
        return {"items": [await self._serialize(r, target) for r in records]}

    async def get_summary(self) -> dict[str, Any]:
        """Real org-wide summary: how many staff have an active/approved pass, how many need one returned."""
        records = await BaseAccessRecord.find().to_list()
        today = date.today()
        latest_by_user: dict[Any, BaseAccessRecord] = {}
        for record in records:
            existing = latest_by_user.get(record.user_id)
            if existing is None or record.created_at > existing.created_at:
                latest_by_user[record.user_id] = record

        approved_count = 0
        expired_count = 0
        pending_return_count = 0
        for record in latest_by_user.values():
            if record.approval_status == "approved":
                if record.expiration_date and record.expiration_date < today:
                    expired_count += 1
                else:
                    approved_count += 1
            if record.return_required and record.expiration_date and record.expiration_date < today and record.returned_date is None:
                pending_return_count += 1

        return {
            "tracked_staff_count": len(latest_by_user),
            "approved_count": approved_count,
            "expired_count": expired_count,
            "pending_return_count": pending_return_count,
            "checked_at": utc_now().isoformat(),
        }

    async def _serialize(self, record: BaseAccessRecord, target: User) -> dict[str, Any]:
        today = date.today()
        is_expired = bool(record.expiration_date and record.expiration_date < today)
        return {
            "id": str(record.id),
            "user_id": str(record.user_id),
            "user_name": target.full_name,
            "request_date": record.request_date.isoformat(),
            "approval_status": record.approval_status,
            "expiration_date": record.expiration_date.isoformat() if record.expiration_date else None,
            "return_required": record.return_required,
            "returned_date": record.returned_date.isoformat() if record.returned_date else None,
            "is_expired": is_expired,
            "updated_at": record.updated_at.isoformat(),
        }
