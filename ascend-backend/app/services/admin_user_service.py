"""Admin user-management service (DOCX Admin Panel: "Assign roles, coaches,
specialists, teams, units, reporting groups, and support pathways.").

Every role change and manual provider assignment is audit logged -
previously nothing in this backend recorded role changes at all.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.roles import SUPPORTED_ROLES, normalize_role
from app.core.security import utc_now
from app.core.support_pathways import get_support_pathway
from app.models.team_assignment import TeamAssignment
from app.models.user import User
from app.schemas.admin_user import ProviderAssignRequest, RoleChangeRequest, UnitAssignRequest
from app.services.audit_log_service import AuditLogService

STATUS_ENABLED = "enabled"
STATUS_LOCKED_ON = "locked_on"


class AdminUserService:
    """List users and manage role/unit/provider assignments."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()

    async def list_users(self, role_filter: str | None = None) -> dict[str, Any]:
        """Return every user, optionally filtered by role."""
        if role_filter:
            users = await User.find(User.role == normalize_role(role_filter)).to_list()
        else:
            users = await User.find().to_list()
        users.sort(key=lambda item: item.email)
        return {"users": [self._serialize(u) for u in users]}

    async def change_role(self, admin: User, user_id: str, payload: RoleChangeRequest) -> dict[str, Any]:
        """Admin changes a user's role. Audit logged."""
        target = await User.get(user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        new_role = normalize_role(payload.role)
        if new_role not in SUPPORTED_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Unsupported role.", "allowed": list(SUPPORTED_ROLES)},
            )

        old_role = target.role
        target.role = new_role
        target.updated_at = utc_now()
        await target.save()

        await self.audit_log_service.record(
            event_type="role_changed",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="user",
            target_entity_id=str(target.id),
            summary_message=f"Role changed from {old_role} to {new_role}.",
            metadata_payload={"old_role": old_role, "new_role": new_role},
        )
        return self._serialize(target)

    async def assign_unit(self, admin: User, user_id: str, payload: UnitAssignRequest) -> dict[str, Any]:
        """Admin assigns a user to a unit. Audit logged."""
        target = await User.get(user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        old_unit = target.unit_id
        target.unit_id = payload.unit_id
        target.updated_at = utc_now()
        await target.save()

        await self.audit_log_service.record(
            event_type="unit_assigned",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="user",
            target_entity_id=str(target.id),
            summary_message=f"Unit changed from {old_unit or '(none)'} to {payload.unit_id or '(none)'}.",
            metadata_payload={"old_unit_id": old_unit, "new_unit_id": payload.unit_id},
        )
        return self._serialize(target)

    async def assign_provider(
        self, admin: User, user_id: str, payload: ProviderAssignRequest
    ) -> dict[str, Any]:
        """Admin manually assigns/overrides a pathway's provider for a user. Audit logged."""
        target = await User.get(user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        pathway = get_support_pathway(payload.pathway_key)
        if pathway is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown pathway.")
        provider = await User.get(payload.provider_user_id)
        if provider is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found.")

        assignment = await TeamAssignment.find_one(
            TeamAssignment.user_id == target.id, TeamAssignment.pathway_key == payload.pathway_key
        )
        previous_provider_id = assignment.provider_user_id if assignment else None
        if assignment is None:
            assignment = TeamAssignment(
                user_id=target.id,
                pathway_key=payload.pathway_key,
                status=STATUS_LOCKED_ON if pathway["always_available"] else STATUS_ENABLED,
            )
        assignment.provider_user_id = provider.id
        assignment.updated_at = utc_now()
        await assignment.save()

        await self.audit_log_service.record(
            event_type="provider_assigned",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="team_assignment",
            target_entity_id=str(assignment.id),
            summary_message=f"{pathway['label']} provider manually assigned to {provider.full_name}.",
            metadata_payload={
                "pathway_key": payload.pathway_key,
                "previous_provider_id": str(previous_provider_id) if previous_provider_id else None,
                "new_provider_id": str(provider.id),
            },
        )
        return {
            "pathway_key": payload.pathway_key,
            "provider": {"user_id": str(provider.id), "name": provider.full_name},
        }

    def _serialize(self, user: User) -> dict[str, Any]:
        """Convert a user to the Admin user-list transport-safe dict."""
        return {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "unit_id": user.unit_id,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
        }
