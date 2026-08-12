"""Org unit hierarchy service (see `app/models/org_unit.py` for why this exists)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.models.org_unit import UNIT_TYPES, OrgUnit
from app.models.user import User
from app.schemas.org_unit import OrgUnitCreate
from app.services.audit_log_service import AuditLogService


class OrgUnitService:
    """Create and list real org units, resolving parent -> child hierarchy."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()

    async def create(self, admin: User, payload: OrgUnitCreate) -> dict[str, Any]:
        """Create a real org unit. Audit logged."""
        if payload.unit_type not in UNIT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Unsupported unit_type.", "allowed": list(UNIT_TYPES)},
            )
        parent = None
        if payload.parent_id:
            parent = await OrgUnit.get(payload.parent_id)
            if parent is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent unit not found.")

        unit = OrgUnit(name=payload.name, unit_type=payload.unit_type, parent_id=parent.id if parent else None)
        await unit.insert()

        await self.audit_log_service.record(
            event_type="org_unit_created",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="org_unit",
            target_entity_id=str(unit.id),
            summary_message=f"Created {payload.unit_type} '{payload.name}'.",
            metadata_payload={"unit_type": payload.unit_type, "parent_id": payload.parent_id},
        )
        return await self._serialize(unit)

    async def list_all(self) -> dict[str, Any]:
        """Return every org unit with its resolved ancestor path."""
        units = await OrgUnit.find().to_list()
        return {"units": [await self._serialize(u, all_units=units) for u in units]}

    async def resolve_ancestors(self, unit_id: str) -> list[dict[str, Any]]:
        """Return the ancestor chain (root-first) for a real org unit id."""
        units = await OrgUnit.find().to_list()
        by_id = {str(u.id): u for u in units}
        chain: list[dict[str, Any]] = []
        current = by_id.get(unit_id)
        while current is not None:
            chain.insert(0, {"id": str(current.id), "name": current.name, "unit_type": current.unit_type})
            current = by_id.get(str(current.parent_id)) if current.parent_id else None
        return chain

    async def _serialize(self, unit: OrgUnit, all_units: list[OrgUnit] | None = None) -> dict[str, Any]:
        ancestor_path = await self.resolve_ancestors(str(unit.id))
        return {
            "id": str(unit.id),
            "name": unit.name,
            "unit_type": unit.unit_type,
            "parent_id": str(unit.parent_id) if unit.parent_id else None,
            "ancestor_path": [a["name"] for a in ancestor_path],
        }
