"""Fly Away Kit service (DOCX section 8.6, Fly Away HPO Kit Support).

Combines three real sources - never fabricated: the unit's admin-configured
emergency contact directory (`EmergencyContactConfig`, null until an Admin
sets it), the user's `ReconditioningPlan` (null until PT/IM or SCS creates
one), and the real auto-assigned SCS/PT-IM providers already used by My
Support Team.
"""

from __future__ import annotations

from typing import Any

from app.core.security import utc_now
from app.models.emergency_contact_config import EmergencyContactConfig
from app.models.team_assignment import TeamAssignment
from app.models.user import User
from app.schemas.emergency_contact import EmergencyContactUpdate
from app.services.reconditioning_service import ReconditioningService


class FlyAwayKitService:
    """Build the Fly Away Kit screen payload."""

    def __init__(self) -> None:
        self.reconditioning_service = ReconditioningService()

    async def get_for_user(self, user: User) -> dict[str, Any]:
        """Return the Fly Away Kit view for an operator."""
        contacts = None
        if user.unit_id:
            config = await EmergencyContactConfig.find_one(
                EmergencyContactConfig.unit_id == user.unit_id
            )
            if config is not None:
                contacts = {
                    "scs_on_call_phone": config.scs_on_call_phone,
                    "ptim_clinic_phone": config.ptim_clinic_phone,
                    "ptim_clinic_hours": config.ptim_clinic_hours,
                    "chaplain_hotline_phone": config.chaplain_hotline_phone,
                    "family_contact_note": config.family_contact_note,
                }

        rehab_status = await self.reconditioning_service.get_for_user(user.id)

        assigned_ptim = None
        assignment = await TeamAssignment.find_one(
            TeamAssignment.user_id == user.id, TeamAssignment.pathway_key == "PT/IM"
        )
        if assignment is not None and assignment.provider_user_id is not None:
            provider = await User.get(assignment.provider_user_id)
            if provider is not None:
                assigned_ptim = {"user_id": str(provider.id), "name": provider.full_name}

        return {
            "emergency_contacts": contacts,
            "rehab_status": rehab_status,
            "assigned_provider": assigned_ptim,
        }

    async def upsert_emergency_contacts(
        self, unit_id: str, payload: EmergencyContactUpdate, updated_by: Any
    ) -> dict[str, Any]:
        """Admin sets/updates a unit's emergency contact directory."""
        config = await EmergencyContactConfig.find_one(EmergencyContactConfig.unit_id == unit_id)
        if config is None:
            config = EmergencyContactConfig(unit_id=unit_id)

        config.scs_on_call_phone = payload.scs_on_call_phone
        config.ptim_clinic_phone = payload.ptim_clinic_phone
        config.ptim_clinic_hours = payload.ptim_clinic_hours
        config.chaplain_hotline_phone = payload.chaplain_hotline_phone
        config.family_contact_note = payload.family_contact_note
        config.updated_by = updated_by
        config.updated_at = utc_now()
        await config.save()

        return {
            "unit_id": config.unit_id,
            "scs_on_call_phone": config.scs_on_call_phone,
            "ptim_clinic_phone": config.ptim_clinic_phone,
            "ptim_clinic_hours": config.ptim_clinic_hours,
            "chaplain_hotline_phone": config.chaplain_hotline_phone,
            "family_contact_note": config.family_contact_note,
            "updated_at": config.updated_at.isoformat(),
        }
