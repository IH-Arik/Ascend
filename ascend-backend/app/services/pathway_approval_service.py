"""Approval/enablement service for the 3 optional support pathways.

See `app/models/pathway_approval.py` for why this exists. Only the 3
optional pathways (Nutritionist, Mental Performance, Chaplain) go through
this lifecycle - `SCS`/`PT/IM` are `always_available` and never gated on
approval, so both actions 400 for them.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.security import utc_now
from app.core.support_pathways import get_support_pathway, get_support_pathways
from app.models.pathway_approval import STATUS_APPROVED, STATUS_ENABLED, STATUS_PENDING, PathwayApproval
from app.models.user import User
from app.schemas.pathway_approval import PathwayEnableRequest
from app.services.audit_log_service import AuditLogService


class PathwayApprovalService:
    """Approve, enable, and read the real per-pathway approval lifecycle."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()

    def _validate_optional_pathway(self, pathway_key: str) -> None:
        pathway = get_support_pathway(pathway_key)
        if pathway is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown pathway.")
        if pathway["always_available"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{pathway_key} is always available and does not go through approval.",
            )

    async def get_status(self, pathway_key: str) -> dict[str, Any]:
        """Return a pathway's real approval/enablement state, honestly `pending` if never touched."""
        record = await PathwayApproval.find_one(PathwayApproval.pathway_key == pathway_key)
        if record is None:
            return {
                "pathway_key": pathway_key,
                "status": STATUS_PENDING,
                "approved_by": None,
                "approved_at": None,
                "enabled_by": None,
                "enabled_at": None,
                "access_policy": None,
            }
        return self._serialize(record)

    async def list_all(self) -> dict[str, Any]:
        """Return every optional pathway's real approval/enablement state."""
        optional_keys = [p["key"] for p in get_support_pathways() if not p["always_available"]]
        return {"pathways": [await self.get_status(key) for key in optional_keys]}

    async def approve(self, actor: User, pathway_key: str) -> dict[str, Any]:
        """Admin/Superadmin approves an optional pathway. Audit logged."""
        self._validate_optional_pathway(pathway_key)
        record = await PathwayApproval.find_one(PathwayApproval.pathway_key == pathway_key)
        if record is None:
            record = PathwayApproval(pathway_key=pathway_key)

        record.status = STATUS_APPROVED
        record.approved_by = actor.id
        record.approved_at = utc_now()
        await record.save()

        await self.audit_log_service.record(
            event_type="pathway_approved",
            actor_id=actor.id,
            actor_role=actor.role,
            target_entity_type="pathway_approval",
            target_entity_id=str(record.id),
            summary_message=f"{actor.role} approved the {pathway_key} pathway.",
            metadata_payload={"pathway_key": pathway_key},
        )
        return self._serialize(record)

    async def enable(self, actor: User, pathway_key: str, payload: PathwayEnableRequest) -> dict[str, Any]:
        """Admin/Superadmin enables a previously-approved pathway. Audit logged."""
        self._validate_optional_pathway(pathway_key)
        record = await PathwayApproval.find_one(PathwayApproval.pathway_key == pathway_key)
        if record is None or record.status == STATUS_PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This pathway must be approved before it can be enabled.",
            )

        record.status = STATUS_ENABLED
        record.enabled_by = actor.id
        record.enabled_at = utc_now()
        record.access_policy = payload.access_policy
        await record.save()

        await self.audit_log_service.record(
            event_type="pathway_enabled",
            actor_id=actor.id,
            actor_role=actor.role,
            target_entity_type="pathway_approval",
            target_entity_id=str(record.id),
            summary_message=f"{actor.role} enabled the {pathway_key} pathway.",
            metadata_payload={"pathway_key": pathway_key, "access_policy": payload.access_policy},
        )
        return self._serialize(record)

    def _serialize(self, record: PathwayApproval) -> dict[str, Any]:
        return {
            "pathway_key": record.pathway_key,
            "status": record.status,
            "approved_by": str(record.approved_by) if record.approved_by else None,
            "approved_at": record.approved_at.isoformat() if record.approved_at else None,
            "enabled_by": str(record.enabled_by) if record.enabled_by else None,
            "enabled_at": record.enabled_at.isoformat() if record.enabled_at else None,
            "access_policy": record.access_policy,
        }
