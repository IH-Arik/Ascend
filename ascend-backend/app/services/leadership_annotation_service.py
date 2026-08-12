"""Leadership "Annotated events" editorial timeline service (see
`app/models/leadership_annotation.py` for why this exists - real,
human-authored narrative content, not a computed aggregate).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException, status

from app.models.leadership_annotation import LeadershipAnnotation
from app.models.user import User
from app.schemas.leadership_annotation import LeadershipAnnotationCreate
from app.services.audit_log_service import AuditLogService


class LeadershipAnnotationService:
    """Create, list, and delete real leadership-authored editorial annotations."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()

    async def create(self, author: User, payload: LeadershipAnnotationCreate) -> dict[str, Any]:
        """Author a real editorial annotation. Audit logged."""
        record = LeadershipAnnotation(
            title=payload.title,
            narrative=payload.narrative,
            event_date=payload.event_date,
            unit_id=payload.unit_id,
            created_by=author.id,
        )
        await record.insert()

        await self.audit_log_service.record(
            event_type="leadership_annotation_created",
            actor_id=author.id,
            actor_role=author.role,
            target_entity_type="leadership_annotation",
            target_entity_id=str(record.id),
            summary_message=f"Authored annotation '{record.title}' for {record.event_date.isoformat()}.",
            metadata_payload={"unit_id": record.unit_id},
        )
        return await self._serialize(record)

    async def list_for_period(self, period_start: date, period_end: date) -> dict[str, Any]:
        """Return real annotations whose event_date falls within a period, newest first."""
        records = await LeadershipAnnotation.find(
            LeadershipAnnotation.event_date >= period_start,
            LeadershipAnnotation.event_date <= period_end,
        ).to_list()
        records.sort(key=lambda item: item.event_date, reverse=True)
        return {"annotations": [await self._serialize(r) for r in records]}

    async def delete(self, annotation_id: str, actor: User) -> None:
        """Delete a real annotation. Admin/Superadmin-only (route-gated). Audit logged."""
        record = await LeadershipAnnotation.get(annotation_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found.")

        await self.audit_log_service.record(
            event_type="leadership_annotation_deleted",
            actor_id=actor.id,
            actor_role=actor.role,
            target_entity_type="leadership_annotation",
            target_entity_id=str(record.id),
            summary_message=f"Deleted annotation '{record.title}' ({record.event_date.isoformat()}).",
        )
        await record.delete()

    async def _serialize(self, record: LeadershipAnnotation) -> dict[str, Any]:
        """Convert a stored annotation to a transport-safe dict."""
        author = await User.get(record.created_by)
        return {
            "id": str(record.id),
            "title": record.title,
            "narrative": record.narrative,
            "event_date": record.event_date.isoformat(),
            "unit_id": record.unit_id,
            "created_by_name": author.full_name if author else None,
            "created_at": record.created_at.isoformat(),
        }
