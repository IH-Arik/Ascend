"""My Support Team service (DOCX "My Support Team" module).

SCS/PT-IM assignment is best-effort auto-assignment to the first active
user with that system role - there is no load-balancing/roster-management
system yet (docx envisions "assignment to coach/specialist/team/unit/
reporting group" as an admin-managed capability, which doesn't exist here).
If no such provider account exists yet, the pathway honestly reports
"not yet assigned" rather than fabricating a name.

An optional pathway's first-ever assignment record seeds its "enabled" state
from the user's onboarding opt-in (`SupportService.get_opted_in_pathways`),
so choosing a pathway during onboarding is reflected here without requiring
a separate toggle. This is a one-time seed at record-creation, not a live
sync - if onboarding is completed after this screen has already been opened
once, the operator needs to toggle it on manually.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.security import utc_now
from app.core.support_pathways import get_support_pathway, get_support_pathways
from app.models.recommendation import Recommendation
from app.models.support_request import SupportRequest
from app.models.team_assignment import STATUS_DISABLED, STATUS_ENABLED, STATUS_LOCKED_ON, TeamAssignment
from app.models.user import User
from app.services.audit_log_service import AuditLogService
from app.services.support_service import SupportService


class TeamService:
    """Return and manage a user's My Support Team pathway assignments."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()
        self.support_service = SupportService()

    async def get_my_team(self, user: User) -> dict[str, Any]:
        """Return every pathway with its assignment/enable state."""
        pathways = []
        for pathway in get_support_pathways():
            assignment = await self._get_or_create_assignment(user, pathway)
            provider = (
                await User.get(assignment.provider_user_id)
                if assignment.provider_user_id
                else None
            )
            latest_request = await self._get_latest_support_request(user, pathway["key"])
            assigned_action = await self._get_matching_active_action(user, pathway["key"])
            pathways.append(
                self._serialize_pathway_status(
                    pathway, assignment, provider, latest_request, assigned_action
                )
            )
        return {"pathways": pathways}

    async def toggle_pathway(self, user: User, pathway_key: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable an optional pathway. Audit logged."""
        pathway = get_support_pathway(pathway_key)
        if pathway is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown pathway.")
        if pathway["always_available"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{pathway['label']} is assigned automatically and cannot be disabled.",
            )

        assignment = await self._get_or_create_assignment(user, pathway)
        previous_status = assignment.status
        assignment.status = STATUS_ENABLED if enabled else STATUS_DISABLED
        assignment.updated_at = utc_now()
        await assignment.save()

        await self.audit_log_service.record(
            event_type="support_pathway_toggle",
            actor_id=user.id,
            actor_role=user.role,
            target_entity_type="team_assignment",
            target_entity_id=str(assignment.id),
            summary_message=f"{'Enabled' if enabled else 'Disabled'} the {pathway['label']} support pathway.",
            metadata_payload={
                "pathway_key": pathway_key,
                "previous_status": previous_status,
                "new_status": assignment.status,
            },
        )

        provider = (
            await User.get(assignment.provider_user_id) if assignment.provider_user_id else None
        )
        latest_request = await self._get_latest_support_request(user, pathway_key)
        assigned_action = await self._get_matching_active_action(user, pathway_key)
        return self._serialize_pathway_status(
            pathway, assignment, provider, latest_request, assigned_action
        )

    async def _get_or_create_assignment(self, user: User, pathway: dict[str, Any]) -> TeamAssignment:
        """Return the existing assignment for a pathway, creating one if needed."""
        existing = await TeamAssignment.find_one(
            TeamAssignment.user_id == user.id, TeamAssignment.pathway_key == pathway["key"]
        )
        if existing is not None:
            if existing.provider_user_id is None and pathway["role"] is not None:
                # Not gated to `always_available` - an optional pathway's
                # assignment record can predate its role becoming real (as
                # happened when Nutritionist/Mental Performance/Chaplain
                # were added), so every pathway retries here, not just the
                # 2 locked-on ones.
                provider = await self._find_active_provider(pathway["role"])
                if provider is not None:
                    existing.provider_user_id = provider.id
                    existing.updated_at = utc_now()
                    await existing.save()
            return existing

        provider_user_id = None
        if pathway["role"] is not None:
            provider = await self._find_active_provider(pathway["role"])
            if provider is not None:
                provider_user_id = provider.id

        if pathway["always_available"]:
            initial_status = STATUS_LOCKED_ON
        else:
            opted_in = await self.support_service.get_opted_in_pathways(user)
            initial_status = STATUS_ENABLED if pathway["key"] in opted_in else STATUS_DISABLED

        record = TeamAssignment(
            user_id=user.id,
            pathway_key=pathway["key"],
            provider_user_id=provider_user_id,
            status=initial_status,
        )
        await record.insert()
        return record

    async def _find_active_provider(self, role: str) -> User | None:
        """Return the first active user with a given provider role, if any exists."""
        candidates = await User.find(User.role == role).to_list()
        active = [u for u in candidates if u.is_active]
        return active[0] if active else None

    async def _get_latest_support_request(
        self, user: User, pathway_key: str
    ) -> SupportRequest | None:
        """Return the most recent support request the user made to a pathway, if any."""
        records = await SupportRequest.find(
            SupportRequest.user_id == user.id, SupportRequest.pathway_key == pathway_key
        ).to_list()
        if not records:
            return None
        return max(records, key=lambda item: item.created_at)

    async def _get_matching_active_action(
        self, user: User, pathway_key: str
    ) -> Recommendation | None:
        """Return the active recommendation/assigned action routed to a pathway, if any."""
        records = await Recommendation.find(
            Recommendation.user_id == user.id,
            Recommendation.status == "active",
            Recommendation.specialist_route == pathway_key,
        ).to_list()
        if not records:
            return None
        return max(records, key=lambda item: item.created_at)

    def _serialize_pathway_status(
        self,
        pathway: dict[str, Any],
        assignment: TeamAssignment,
        provider: User | None,
        latest_request: SupportRequest | None,
        assigned_action: Recommendation | None,
    ) -> dict[str, Any]:
        """Build the transport-safe pathway status entry."""
        return {
            "pathway_key": pathway["key"],
            "label": pathway["label"],
            "role_title": pathway["role_title"],
            "description": pathway["description"],
            "always_available": pathway["always_available"],
            "status": assignment.status,
            "messaging_available": pathway["messaging_v1_supported"]
            and assignment.status in (STATUS_LOCKED_ON, STATUS_ENABLED),
            "provider": (
                {
                    "user_id": str(provider.id),
                    "name": provider.full_name,
                }
                if provider is not None
                else None
            ),
            "follow_up_status": (
                {
                    "request_id": str(latest_request.id),
                    "status": latest_request.status,
                    "created_at": latest_request.created_at.isoformat(),
                }
                if latest_request is not None
                else None
            ),
            "assigned_action": (
                {
                    "id": str(assigned_action.id),
                    "title": assigned_action.title,
                    "status": assigned_action.status,
                    "due_date": (
                        assigned_action.due_date.isoformat()
                        if assigned_action.due_date
                        else None
                    ),
                }
                if assigned_action is not None
                else None
            ),
        }
